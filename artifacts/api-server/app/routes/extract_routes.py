import threading
import time
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
        "progress": 0,
        "done": False,
        "error": None,
        "result": None,
        "phase": "scan",
        "articles_done": 0,
        "articles_total": 0,
        "previews_done": 0,
        "previews_total": 0,
        "start_time": time.time(),
        "elapsed": 0,
    }

    def run_extraction():
        def progress_cb(pct, articles_done=None, articles_total=None):
            p = _extraction_progress[batch_id]
            p["progress"] = pct
            p["elapsed"] = round(time.time() - p["start_time"], 1)
            if articles_done is not None:
                p["articles_done"] = articles_done
            if articles_total is not None:
                p["articles_total"] = articles_total
            if pct < 50:
                p["phase"] = "scan"
            elif pct < 96:
                p["phase"] = "extract"

        try:
            result = extract_zip(batch_id, Path(archive_path), progress_cb=progress_cb)
            _extraction_progress[batch_id]["result"] = result
            if result["ok"]:
                _extraction_progress[batch_id]["phase"] = "previews"
                meta2 = load_metadata(batch_id)
                if meta2:
                    def preview_cb(done, total):
                        p = _extraction_progress[batch_id]
                        p["previews_done"] = done
                        p["previews_total"] = total
                        p["elapsed"] = round(time.time() - p["start_time"], 1)
                    generate_all_previews(batch_id, meta2.get("articles", {}), progress_cb=preview_cb)
                    log_event(batch_id, "info", "Превью созданы")
            p = _extraction_progress[batch_id]
            p["progress"] = 100
            p["done"] = True
            p["phase"] = "done"
            p["elapsed"] = round(time.time() - p["start_time"], 1)
        except Exception as e:
            p = _extraction_progress[batch_id]
            p["error"] = str(e)
            p["done"] = True
            p["phase"] = "error"
            p["elapsed"] = round(time.time() - p["start_time"], 1)
            log_event(batch_id, "error", f"Ошибка распаковки: {e}")

    t = threading.Thread(target=run_extraction, daemon=True)
    t.start()

    return JSONResponse({"ok": True, "message": "Распаковка начата"})


@router.get("/batch/{batch_id}/extract/progress")
async def extraction_progress(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    prog = _extraction_progress.get(batch_id, {
        "progress": 0, "done": False, "error": None, "result": None,
        "phase": "scan", "articles_done": 0, "articles_total": 0, "elapsed": 0,
    })
    phase = prog.get("phase", "scan")
    adone = prog.get("articles_done", 0)
    atotal = prog.get("articles_total", 0)
    elapsed = prog.get("elapsed", 0)

    if phase == "scan":
        status_msg = "Сканирование архива..."
    elif phase == "extract":
        if atotal:
            status_msg = f"Распаковано {adone} из {atotal} артикулов..."
        else:
            status_msg = "Обработка изображений..."
    elif phase == "previews":
        pdone = prog.get("previews_done", 0)
        ptotal = prog.get("previews_total", 0)
        if ptotal:
            status_msg = f"Создание превью {pdone} из {ptotal}..."
        else:
            status_msg = "Создание превью..."
    elif phase == "done":
        status_msg = "Готово"
    else:
        status_msg = "Ошибка"

    return JSONResponse({**prog, "status_msg": status_msg, "elapsed": elapsed})
