from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.metadata import list_all_batches, load_metadata, save_metadata
from app.logger_utils import get_log
from app.cleanup import delete_batch

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    batches = list_all_batches()
    return templates.TemplateResponse(request, "history.html", {
        "user": current_user(request),
        "batches": batches,
    })


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, batch_id: str = None):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    batches = list_all_batches()
    log_entries = []
    selected_batch = None
    if batch_id:
        log_entries = get_log(batch_id)
        selected_batch = load_metadata(batch_id)
    return templates.TemplateResponse(request, "logs_page.html", {
        "user": current_user(request),
        "batches": batches,
        "log_entries": log_entries,
        "selected_batch_id": batch_id,
        "selected_batch": selected_batch,
    })


@router.get("/batch/{batch_id}/download-log")
async def download_log(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    from app.config import LOGS_DIR
    entries = get_log(batch_id)
    meta = load_metadata(batch_id)
    name = meta.get("name", batch_id) if meta else batch_id
    path = LOGS_DIR / f"{batch_id}_export.txt"
    with open(path, 'w', encoding='utf-8') as f:
        for e in entries:
            f.write(f"[{e.get('ts','')}] [{e.get('level','').upper()}] {e.get('message','')}\n")
    return FileResponse(path, filename=f"{name}_log.txt", media_type="text/plain")


@router.post("/batch/{batch_id}/rename")
async def rename_batch(request: Request, batch_id: str, new_name: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/history", status_code=302)
    from datetime import datetime
    date_str = datetime.utcnow().strftime("%d-%m-%Y")
    full_name = f"{new_name}_{date_str}"
    meta["display_name"] = new_name
    meta["name"] = full_name
    save_metadata(batch_id, meta)
    from app.logger_utils import log_event
    log_event(batch_id, "info", f"Партия переименована в: {full_name}")
    return RedirectResponse(url="/history", status_code=302)


@router.post("/batch/{batch_id}/delete")
async def delete_batch_route(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    delete_batch(batch_id)
    return RedirectResponse(url="/history?deleted=1", status_code=302)


@router.get("/batch/{batch_id}/download-csv")
async def download_csv(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/history", status_code=302)
    csv_path = meta.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        from app.csv_export import generate_csv
        import os
        base_url = os.environ.get("BASE_URL", "")
        result = generate_csv(batch_id, base_url)
        if not result["ok"]:
            return RedirectResponse(url="/history", status_code=302)
        meta = load_metadata(batch_id)
        csv_path = meta.get("csv_path")
    if not csv_path or not Path(csv_path).exists():
        return RedirectResponse(url="/history", status_code=302)
    filename = meta.get("csv_filename", f"{batch_id}.csv")
    return FileResponse(csv_path, filename=filename, media_type="text/csv")
