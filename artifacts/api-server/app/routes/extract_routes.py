import threading
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.config import UPLOADS_DIR
from app.metadata import load_metadata, save_metadata
from app.extractor import extract_zip
from app.logger_utils import log_event
from app.preview_gen import generate_all_previews

from app.templates import templates
router = APIRouter()

# In-memory extraction progress store
_extraction_progress: dict[str, dict] = {}

_PHASE_LABELS = {
    "scan": "Сканирование архива...",
    "extract": "Обработка изображений...",
    "previews": "Создание превью...",
    "done": "Готово",
    "error": "Ошибка",
}


@router.post("/batch/{batch_id}/extract")
async def start_extraction(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False, "error": "Не авторизован"}, status_code=401)

    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "Партия не найдена"}, status_code=404)

    archive_path = meta.get("archive_path")
    if not archive_path or not Path(archive_path).exists():
        return JSONResponse({"ok": False, "error": "Архив не найден. Загрузите архив."}, status_code=400)

    _extraction_progress[batch_id] = {
        "progress": 0, "done": False, "error": None, "result": None, "phase": "scan"
    }

    def run_extraction():
        def progress_cb(pct):
            _extraction_progress[batch_id]["progress"] = pct
            if pct < 50:
                _extraction_progress[batch_id]["phase"] = "scan"
            elif pct < 100:
                _extraction_progress[batch_id]["phase"] = "extract"

        try:
            result = extract_zip(batch_id, Path(archive_path), progress_cb=progress_cb)
            _extraction_progress[batch_id]["result"] = result
            if result["ok"]:
                _extraction_progress[batch_id]["phase"] = "previews"
                meta2 = load_metadata(batch_id)
                if meta2:
                    generate_all_previews(batch_id, meta2.get("articles", {}))
                    log_event(batch_id, "info", "Превью созданы")
            _extraction_progress[batch_id]["progress"] = 100
            _extraction_progress[batch_id]["done"] = True
            _extraction_progress[batch_id]["phase"] = "done"
        except Exception as e:
            _extraction_progress[batch_id]["error"] = str(e)
            _extraction_progress[batch_id]["done"] = True
            _extraction_progress[batch_id]["phase"] = "error"
            log_event(batch_id, "error", f"Ошибка распаковки: {e}")

    t = threading.Thread(target=run_extraction, daemon=True)
    t.start()

    return JSONResponse({"ok": True, "message": "Распаковка начата"})


@router.get("/batch/{batch_id}/extract/progress")
async def extraction_progress(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    prog = _extraction_progress.get(batch_id, {
        "progress": 0, "done": False, "error": None, "result": None, "phase": "scan"
    })
    status_msg = _PHASE_LABELS.get(prog.get("phase", "scan"), "Распаковка архива...")
    return JSONResponse({**prog, "status_msg": status_msg})
