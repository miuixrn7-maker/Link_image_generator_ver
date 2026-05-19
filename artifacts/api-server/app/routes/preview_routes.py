import os
import io
from pathlib import Path
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse


from app.auth import is_authenticated, current_user
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event
from app.csv_export import generate_csv
from app.preview_gen import generate_preview
from app.config import BATCHES_DIR, MAX_IMAGE_SIZE_BYTES
from app.utils import safe_filename, make_unique_filename

from app.templates import templates
router = APIRouter()

_ALLOWED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}


def _make_manual_filename(safe_name: str, existing: set) -> str:
    if safe_name not in existing:
        return safe_name
    stem = Path(safe_name).stem
    ext = Path(safe_name).suffix
    candidate = f"{stem}_manual{ext}"
    if candidate not in existing:
        return candidate
    i = 2
    while True:
        candidate = f"{stem}_manual_{i}{ext}"
        if candidate not in existing:
            return candidate
        i += 1


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
    base_url = os.environ.get("BASE_URL", "").strip()
    if not base_url:
        host = request.headers.get("host") or request.url.netloc
        base_url = f"{request.url.scheme}://{host}"
    result = generate_csv(batch_id, base_url)
    return JSONResponse(result)


@router.post("/batch/{batch_id}/api/rename-article")
async def rename_article_api(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    article_id = body.get("article_id", "").strip()
    new_display = body.get("new_display", "").strip()
    if not article_id or not new_display:
        return JSONResponse({"ok": False, "error": "Недостаточно данных"}, status_code=400)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    articles = meta.get("articles", {})
    if article_id not in articles:
        return JSONResponse({"ok": False, "error": "Артикул не найден"}, status_code=404)
    old_display = articles[article_id].get("display_article", article_id)
    articles[article_id]["display_article"] = new_display
    meta["articles"] = articles
    ok = save_metadata(batch_id, meta)
    log_event(batch_id, "info", f"Артикул переименован: «{old_display}» → «{new_display}»", article=article_id)
    return JSONResponse({"ok": ok, "new_display": new_display})


@router.post("/batch/{batch_id}/api/clear-rest-all")
async def clear_rest_all(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    articles = meta.get("articles", {})
    deleted_count = 0
    for article_id, article in articles.items():
        assignment = article.get("assignment", {})
        rest = list(assignment.get("rest", []))
        main_f = assignment.get("main")
        zoom_f = assignment.get("zoom")
        for fname in rest:
            if fname in (main_f, zoom_f):
                continue
            fpath = BATCHES_DIR / batch_id / article_id / fname
            try:
                fpath.unlink(missing_ok=True)
                deleted_count += 1
            except Exception:
                pass
            article["files"] = [f for f in article.get("files", []) if f["safe_name"] != fname]
        assignment["rest"] = []
        article["assignment"] = assignment
    meta["articles"] = articles
    save_metadata(batch_id, meta)
    log_event(batch_id, "info", f"Остальные_фото удалены у всех артикулов: {deleted_count} файлов")
    return JSONResponse({"ok": True, "deleted": deleted_count})


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


@router.post("/batch/{batch_id}/api/add-image")
async def add_image(
    request: Request,
    batch_id: str,
    article: str = Form(...),
    column: str = Form(...),
    file: UploadFile = File(...),
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    if column not in ("main", "zoom", "rest"):
        return JSONResponse({"ok": False, "error": "Неверная колонка"}, status_code=400)

    original_name = file.filename or "image.jpg"
    ext = Path(original_name).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        return JSONResponse({"ok": False, "error": "Неподдерживаемый формат файла"})

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Партия не найдена"}, status_code=404)

    articles = meta.get("articles", {})
    if article not in articles:
        return JSONResponse({"ok": False, "error": "Артикул не найден"}, status_code=404)

    a = articles[article]
    files_list = a.get("files", [])

    data = await file.read()
    file_size = len(data)

    safe_name_raw = safe_filename(original_name)
    if not safe_name_raw or safe_name_raw == ext.lstrip('.') or safe_name_raw == ext:
        safe_name_raw = f"image{ext}"

    existing_names = {f["safe_name"] for f in files_list}
    safe_name = _make_manual_filename(safe_name_raw, existing_names)

    # Security: ensure file stays inside batch/article directory
    article_dir = BATCHES_DIR / batch_id / article
    article_dir.mkdir(parents=True, exist_ok=True)
    dest = (article_dir / safe_name).resolve()
    if not str(dest).startswith(str((BATCHES_DIR / batch_id).resolve())):
        return JSONResponse({"ok": False, "error": "Недопустимый путь"}, status_code=400)

    with open(dest, "wb") as f_out:
        f_out.write(data)

    width = height = None
    file_errors = []
    try:
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(data)) as img:
            width, height = img.size
    except Exception:
        file_errors.append("Файл повреждён или не является изображением")

    if file_size > MAX_IMAGE_SIZE_BYTES:
        file_errors.append("Файл больше 10 MB")

    file_obj = {
        "safe_name": safe_name,
        "original_name": original_name,
        "display_name": original_name,
        "size": file_size,
        "width": width,
        "height": height,
        "errors": file_errors,
        "warnings": [],
    }
    files_list.append(file_obj)
    a["files"] = files_list

    assignment = a.setdefault("assignment", {"main": None, "zoom": None, "rest": []})
    if not isinstance(assignment.get("rest"), list):
        assignment["rest"] = []

    displaced = None
    if column == "main":
        old = assignment.get("main")
        if old and old != safe_name:
            displaced = old
            if old not in assignment["rest"]:
                assignment["rest"].append(old)
        assignment["main"] = safe_name
    elif column == "zoom":
        old = assignment.get("zoom")
        if old and old != safe_name:
            displaced = old
            if old not in assignment["rest"]:
                assignment["rest"].append(old)
        assignment["zoom"] = safe_name
    else:
        if safe_name not in assignment["rest"]:
            assignment["rest"].append(safe_name)

    a["assignment"] = assignment

    stats = meta.setdefault("stats", {})
    stats["total_images"] = stats.get("total_images", 0) + 1
    if file_errors:
        stats["total_errors"] = stats.get("total_errors", 0) + len(file_errors)

    save_metadata(batch_id, meta)
    generate_preview(batch_id, article, safe_name, force=True)
    log_event(
        batch_id, "info",
        f"Изображение добавлено вручную: {original_name} → {safe_name}",
        article=article,
    )

    return JSONResponse({
        "ok": True,
        "file": file_obj,
        "assignment": assignment,
        "article_data": a,
        "has_size_error": "Файл больше 10 MB" in file_errors,
        "displaced": displaced,
    })
