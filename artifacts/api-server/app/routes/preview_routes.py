import os
from pathlib import Path
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.auth import is_authenticated, current_user
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event
from app.csv_export import generate_csv
from app.preview_gen import generate_preview
from app.config import BATCHES_DIR, MAX_IMAGE_SIZE_BYTES
from app.utils import safe_filename, make_unique_filename

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/batch/{batch_id}/preview", response_class=HTMLResponse)
async def preview_page(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "preview.html", {
        "user": current_user(request),
        "batch": meta,
    })


@router.get("/batch/{batch_id}/api/meta")
async def get_meta(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Не найдено"}, status_code=404)
    return JSONResponse({"ok": True, "batch": meta})


@router.post("/batch/{batch_id}/api/save-assignment")
async def save_assignment(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Неверный JSON"}, status_code=400)

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Партия не найдена"}, status_code=404)

    articles = meta.get("articles", {})
    updated = body.get("articles", {})

    for article_name, assignment_data in updated.items():
        if article_name in articles:
            articles[article_name]["assignment"] = assignment_data.get("assignment",
                                                                       articles[article_name].get("assignment", {}))

    meta["articles"] = articles
    ok = save_metadata(batch_id, meta)
    return JSONResponse({"ok": ok})


@router.post("/batch/{batch_id}/api/swap/{article}")
async def swap_article(request: Request, batch_id: str, article: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    articles = meta.get("articles", {})
    if article not in articles:
        return JSONResponse({"ok": False, "error": "Артикул не найден"}, status_code=404)
    a = articles[article]
    assignment = a.get("assignment", {})
    main = assignment.get("main")
    zoom = assignment.get("zoom")
    assignment["main"] = zoom
    assignment["zoom"] = main
    a["assignment"] = assignment
    save_metadata(batch_id, meta)
    log_event(batch_id, "info", f"Поменяны местами Главная и Увелич_фото для артикула {article}")
    return JSONResponse({"ok": True, "assignment": assignment})


@router.post("/batch/{batch_id}/api/swap-all")
async def swap_all(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    articles = meta.get("articles", {})
    swapped = []
    for article_name, a in articles.items():
        assignment = a.get("assignment", {})
        main = assignment.get("main")
        zoom = assignment.get("zoom")
        if main and zoom:
            assignment["main"] = zoom
            assignment["zoom"] = main
            a["assignment"] = assignment
            swapped.append(article_name)
    save_metadata(batch_id, meta)
    if swapped:
        log_event(batch_id, "info", f"Поменяны местами Главная и Увелич_фото для {len(swapped)} артикулов")
    return JSONResponse({"ok": True, "swapped": swapped})


@router.post("/batch/{batch_id}/api/rename-file")
async def rename_file(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Неверный JSON"}, status_code=400)

    article_name = body.get("article")
    old_name = body.get("old_name")
    new_stem = body.get("new_name", "").strip()

    if not all([article_name, old_name, new_stem]):
        return JSONResponse({"ok": False, "error": "Недостаточно данных"}, status_code=400)

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)

    articles = meta.get("articles", {})
    if article_name not in articles:
        return JSONResponse({"ok": False, "error": "Артикул не найден"}, status_code=404)

    a = articles[article_name]
    files = a.get("files", [])

    file_obj = next((f for f in files if f["safe_name"] == old_name), None)
    if not file_obj:
        return JSONResponse({"ok": False, "error": "Файл не найден"}, status_code=404)

    ext = Path(old_name).suffix
    new_safe_stem = safe_filename(new_stem + ext).replace(ext, '') or 'file'
    new_name = new_safe_stem + ext

    existing = {f["safe_name"] for f in files if f["safe_name"] != old_name}
    new_name = make_unique_filename(new_name, existing)

    old_path = BATCHES_DIR / batch_id / article_name / old_name
    new_path = BATCHES_DIR / batch_id / article_name / new_name

    if old_path.exists():
        old_path.rename(new_path)

    file_obj["safe_name"] = new_name
    file_obj["display_name"] = new_stem + ext

    assignment = a.get("assignment", {})
    if assignment.get("main") == old_name:
        assignment["main"] = new_name
    if assignment.get("zoom") == old_name:
        assignment["zoom"] = new_name
    rest = assignment.get("rest", [])
    assignment["rest"] = [new_name if r == old_name else r for r in rest]
    a["assignment"] = assignment

    save_metadata(batch_id, meta)
    generate_preview(batch_id, article_name, new_name, force=True)
    log_event(batch_id, "info", f"Изображение переименовано вручную: {old_name} → {new_name}", article=article_name)
    return JSONResponse({"ok": True, "new_name": new_name})


@router.post("/batch/{batch_id}/api/replace-file")
async def replace_file(
    request: Request,
    batch_id: str,
    article: str = Form(...),
    old_name: str = Form(...),
    column: str = Form(...),
    file: UploadFile = File(...),
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)

    articles = meta.get("articles", {})
    if article not in articles:
        return JSONResponse({"ok": False, "error": "Артикул не найден"}, status_code=404)

    a = articles[article]
    files = a.get("files", [])

    data = await file.read()
    file_size = len(data)

    if file_size > MAX_IMAGE_SIZE_BYTES:
        return JSONResponse({"ok": False, "error": "Загруженный файл также больше 10 MB"})

    new_safe = safe_filename(file.filename or old_name)
    existing = {f["safe_name"] for f in files if f["safe_name"] != old_name}
    if new_safe in existing:
        new_safe = make_unique_filename(new_safe, existing)

    dest = BATCHES_DIR / batch_id / article / new_safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, 'wb') as f_out:
        f_out.write(data)

    width = height = None
    new_errors = []
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
    except Exception:
        new_errors.append("Файл повреждён или не является изображением")

    existing_file = next((f for f in files if f["safe_name"] == old_name), None)
    if existing_file:
        old_path = BATCHES_DIR / batch_id / article / old_name
        if old_path.exists() and old_name != new_safe:
            old_path.unlink(missing_ok=True)
        existing_file["safe_name"] = new_safe
        existing_file["display_name"] = file.filename or new_safe
        existing_file["size"] = file_size
        existing_file["width"] = width
        existing_file["height"] = height
        existing_file["errors"] = new_errors

    assignment = a.get("assignment", {})
    if assignment.get("main") == old_name:
        assignment["main"] = new_safe
    if assignment.get("zoom") == old_name:
        assignment["zoom"] = new_safe
    rest = assignment.get("rest", [])
    assignment["rest"] = [new_safe if r == old_name else r for r in rest]
    a["assignment"] = assignment

    save_metadata(batch_id, meta)
    generate_preview(batch_id, article, new_safe, force=True)
    log_event(batch_id, "info", f"Изображение заменено вручную: {old_name} → {new_safe}", article=article)
    return JSONResponse({"ok": True, "new_name": new_safe, "errors": new_errors})


@router.post("/batch/{batch_id}/api/generate-csv")
async def gen_csv(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    base_url = os.environ.get("BASE_URL", "")
    result = generate_csv(batch_id, base_url)
    return JSONResponse(result)


@router.post("/batch/{batch_id}/api/rename-batch")
async def rename_batch_api(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    new_name = body.get("name", "").strip()
    if not new_name:
        return JSONResponse({"ok": False, "error": "Пустое имя"}, status_code=400)
    from datetime import datetime
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    date_str = datetime.utcnow().strftime("%d-%m-%Y")
    full_name = f"{new_name}_{date_str}"
    meta["display_name"] = new_name
    meta["name"] = full_name
    ok = save_metadata(batch_id, meta)
    log_event(batch_id, "info", f"Партия переименована в: {full_name}")
    return JSONResponse({"ok": ok, "name": full_name, "display_name": new_name})
