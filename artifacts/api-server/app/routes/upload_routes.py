import os
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.config import UPLOADS_DIR
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event

from app.templates import templates
router = APIRouter()

# 4 MB write-accumulation buffer — reduces syscall frequency for large files
_WRITE_BUF = 4 * 1024 * 1024
# 8 MB OS-level file buffer for sequential writes
_FILE_BUF = 8 * 1024 * 1024

ZIP_MAGIC = b'PK\x03\x04'
ZIP_EMPTY = b'PK\x05\x06'  # valid empty archive


def _is_zip_magic(first_bytes: bytes) -> bool:
    return first_bytes[:4] in (ZIP_MAGIC, ZIP_EMPTY)


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

    from urllib.parse import unquote
    filename = request.headers.get("X-Filename", "archive.zip")
    try:
        filename = filename.encode('latin-1').decode('utf-8')
    except Exception:
        pass
    filename = unquote(filename)
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
    loop = asyncio.get_event_loop()

    try:
        total_written = 0
        magic_checked = False
        acc = bytearray()  # accumulation buffer

        with open(dest_path, 'wb', buffering=_FILE_BUF) as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                acc.extend(chunk)
                total_written += len(chunk)

                # Check ZIP magic from first bytes without extra open()
                if not magic_checked and total_written >= 4:
                    if not _is_zip_magic(bytes(acc[:4])):
                        # Close and delete before returning
                        f.flush()
                    magic_checked = True

                # Flush accumulation buffer to disk when full
                if len(acc) >= _WRITE_BUF:
                    data = bytes(acc)
                    acc.clear()
                    await loop.run_in_executor(None, f.write, data)

            # Write remaining bytes
            if acc:
                await loop.run_in_executor(None, f.write, bytes(acc))

        if total_written == 0:
            dest_path.unlink(missing_ok=True)
            return JSONResponse({"ok": False, "error": "Файл пустой"}, status_code=400)

        # Validate ZIP magic bytes (read just first 4 bytes from saved file)
        with open(dest_path, 'rb') as f:
            head = f.read(4)
        if not _is_zip_magic(head):
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
