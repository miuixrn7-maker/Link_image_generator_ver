import shutil
from datetime import datetime, timedelta
from pathlib import Path

from app.config import (
    UPLOADS_DIR, BATCHES_DIR, PREVIEWS_DIR, EXPORTS_DIR,
    LOGS_DIR, METADATA_DIR,
)
from app.metadata import load_metadata, save_metadata, list_all_batches, delete_metadata
from app.logger_utils import delete_log, log_event
from app.csv_export import delete_csv
from app.preview_gen import cleanup_old_previews


def delete_batch(batch_id: str) -> dict:
    meta = load_metadata(batch_id)

    def _rm(path: Path):
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    def _count_files(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for _ in path.rglob("*") if _.is_file())
        except Exception:
            return 0

    # Delete ZIP
    if meta:
        archive_path = meta.get("archive_path")
        if archive_path:
            _rm(Path(archive_path))

    # Delete extracted files
    batches_count = _count_files(BATCHES_DIR / batch_id)
    _rm(BATCHES_DIR / batch_id)

    # Delete previews
    previews_count = _count_files(PREVIEWS_DIR / batch_id)
    _rm(PREVIEWS_DIR / batch_id)

    # Delete CSV
    exports_count = 0
    if meta:
        csv_path = meta.get("csv_path")
        if csv_path and Path(csv_path).exists():
            exports_count = 1
            _rm(Path(csv_path))

    # Delete log
    delete_log(batch_id)

    # Delete metadata (last)
    delete_metadata(batch_id)

    parts = []
    if batches_count:
        parts.append(f"изображений: {batches_count}")
    if previews_count:
        parts.append(f"превью: {previews_count}")
    if exports_count:
        parts.append(f"экспортов: {exports_count}")
    summary = "Партия удалена" + (f" ({', '.join(parts)})" if parts else "")

    return {"ok": True, "deleted_previews": previews_count, "deleted_exports": exports_count, "summary": summary}


def auto_cleanup():
    """Delete batches older than configured expire days and clean old previews."""
    cleanup_old_previews()
    expire_days = None
    try:
        from app.settings_manager import get_setting
        expire_days = get_setting("batch_expire_days")
    except Exception:
        expire_days = 14
    if expire_days is None:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=int(expire_days))
    batches = list_all_batches()
    deleted = 0
    for batch in batches:
        created_at = batch.get("created_at", "")
        if not created_at:
            continue
        try:
            dt = datetime.fromisoformat(created_at)
        except Exception:
            continue
        if dt < cutoff:
            delete_batch(batch["id"])
            deleted += 1
    return deleted
