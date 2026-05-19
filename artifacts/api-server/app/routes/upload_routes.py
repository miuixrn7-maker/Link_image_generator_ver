import os
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.config import UPLOADS_DIR
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/batch/{batch_id}/upload", response_class=HTMLResponse)
async def upload_page(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "upload.html", {
        "user": current_user(request),
        "batch": meta,
    })


@router.post("/batch/{batch_id}/upload")
async def upload_archive(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False, "error": "Не авторизован"}, status_code=401)

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Партия не найдена"}, status_code=404)

    filename = request.headers.get("X-Filename", "archive.zip")
    try:
        filename = filename.encode('latin-1').decode('utf-8')
    except Exception:
        pass

    filename_lower = filename.lower()

    if filename_lower.endswith('.rar'):
        return JSONResponse({
            "ok": False,
            "error": "RAR архивы не поддерживаются в версии 1. Загрузите ZIP-архив."
        }, status_code=400)

    if not filename_lower.endswith('.zip'):
        return JSONResponse({"ok": False, "error": "Поддерживаются только ZIP-архивы"}, status_code=400)

    safe_fn = f"{batch_id}.zip"
    dest_path = UPLOADS_DIR / safe_fn

    try:
        total_written = 0
        with open(dest_path, 'wb') as f:
            async for chunk in request.stream():
                f.write(chunk)
                total_written += len(chunk)

        if total_written == 0:
            dest_path.unlink(missing_ok=True)
            return JSONResponse({"ok": False, "error": "Файл пустой"}, status_code=400)

        import zipfile
        if not zipfile.is_zipfile(dest_path):
            dest_path.unlink(missing_ok=True)
            return JSONResponse({
                "ok": False,
                "error": "Файл не является ZIP-архивом или повреждён"
            }, status_code=400)

        meta["archive_name"] = filename
        meta["archive_size"] = total_written
        meta["archive_path"] = str(dest_path)
        meta["status"] = "uploaded"
        save_metadata(batch_id, meta)
        log_event(batch_id, "info", f"Архив загружен: {filename} ({total_written} байт)")

        return JSONResponse({"ok": True, "size": total_written, "filename": filename})

    except Exception as e:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        log_event(batch_id, "error", f"Ошибка загрузки: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.delete("/batch/{batch_id}/upload")
async def cancel_upload(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    zip_path = UPLOADS_DIR / f"{batch_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
    meta = load_metadata(batch_id)
    if meta:
        meta["archive_path"] = None
        meta["archive_name"] = None
        meta["archive_size"] = None
        meta["status"] = "created"
        save_metadata(batch_id, meta)
    log_event(batch_id, "info", "Загрузка отменена пользователем")
    return JSONResponse({"ok": True})


@router.delete("/batch/{batch_id}/archive")
async def delete_archive(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    zip_path = UPLOADS_DIR / f"{batch_id}.zip"
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
    meta = load_metadata(batch_id)
    if meta:
        meta["archive_path"] = None
        meta["archive_name"] = None
        meta["archive_size"] = None
        meta["status"] = "created"
        save_metadata(batch_id, meta)
    return JSONResponse({"ok": True})
