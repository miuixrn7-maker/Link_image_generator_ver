import threading
import time
import zipfile
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pathlib import Path

from app.auth import is_authenticated
from app.config import (
    SUPPORTED_IMAGES,
    WARNING_MAX_ZIP_GB, WARNING_MAX_ARTICLES, WARNING_MAX_IMAGES,
    get_free_disk_space,
)
from app.metadata import load_metadata, save_metadata
from app.extractor import extract_zip
from app.logger_utils import log_event

from app.templates import templates
router = APIRouter()

_extraction_progress: dict[str, dict] = {}


@router.post("/batch/{batch_id}/api/analyze-zip")
async def analyze_zip_archive(request: Request, batch_id: str):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    meta = load_metadata(batch_id)
    if not meta:
        return JSONResponse({"ok": False}, status_code=404)
    archive_path = meta.get("archive_path")
    if not archive_path or not Path(archive_path).exists():
        return JSONResponse({"ok": False, "error": "Архив не найден"})

    zip_path = Path(archive_path)
    zip_size = zip_path.stat().st_size
    zip_gb = zip_size / (1024 ** 3)

    article_count = 0
    image_count = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            article_paths: set = set()
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = info.filename.replace("\\", "/").split("/")
                ext = Path(parts[-1]).suffix.lower()
                if ext in SUPPORTED_IMAGES:
                    image_count += 1
                    if len(parts) >= 2:
                        article_paths.add(parts[-2])
            article_count = len(article_paths)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"Ошибка анализа архива: {e}"})

    free_gb = get_free_disk_space()
    from app.settings_manager import get_setting
    warn_enabled = get_setting("warn_large_archive")
    warn_zip_thresh = float(get_setting("warn_zip_gb") or WARNING_MAX_ZIP_GB)
    warn_articles_thresh = int(get_setting("warn_max_articles") or WARNING_MAX_ARTICLES)
    warn_images_thresh = int(get_setting("warn_max_images") or WARNING_MAX_IMAGES)
    warn_free_thresh = float(get_setting("warn_free_gb") or 15)

    warnings = []
    if warn_enabled is not False:
        if zip_gb >= warn_zip_thresh:
            warnings.append(f"Размер ZIP: {zip_gb:.1f} ГБ (рекомендуемый предел {warn_zip_thresh:.0f} ГБ)")
        if article_count >= warn_articles_thresh:
            warnings.append(f"Артикулов: {article_count} (рекомендуемый предел {warn_articles_thresh})")
        if image_count >= warn_images_thresh:
            warnings.append(f"Изображений: {image_count} (рекомендуемый предел {warn_images_thresh})")
    low_disk = free_gb < max(zip_gb * 2.5 + 0.5, warn_free_thresh)
    if low_disk:
        warnings.append(
            f"Мало свободного места: {free_gb:.1f} ГБ "
            f"(рекомендуется {max(zip_gb*2.5+0.5, warn_free_thresh):.1f} ГБ)"
        )

    return JSONResponse({
        "ok": True,
        "zip_gb": round(zip_gb, 2),
        "zip_size": zip_size,
        "article_count": article_count,
        "image_count": image_count,
        "free_gb": round(free_gb, 2),
        "warnings": warnings,
        "needs_warning": len(warnings) > 0,
        "low_disk": low_disk,
    })


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
            elif pct < 100:
                p["phase"] = "extract"

        try:
            result = extract_zip(batch_id, Path(archive_path), progress_cb=progress_cb)
            _extraction_progress[batch_id]["result"] = result
            p = _extraction_progress[batch_id]
            p["progress"] = 100
            p["done"] = True
            p["phase"] = "done"
            p["elapsed"] = round(time.time() - p["start_time"], 1)
            if result.get("ok"):
                log_event(batch_id, "info", "Распаковка завершена. Превью создаются по запросу.")
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
    elif phase == "done":
        status_msg = "Готово"
    else:
        status_msg = "Ошибка"

    return JSONResponse({**prog, "status_msg": status_msg, "elapsed": elapsed})
