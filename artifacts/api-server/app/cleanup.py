import shutil
from datetime import datetime, timedelta
from pathlib import Path

from app.config import (
    UPLOADS_DIR, BATCHES_DIR, PREVIEWS_DIR, EXPORTS_DIR,
    LOGS_DIR, METADATA_DIR, BATCH_EXPIRE_DAYS
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

    # Delete ZIP
    if meta:
        archive_path = meta.get("archive_path")
        if archive_path:
            _rm(Path(archive_path))

    # Delete extracted files
    _rm(BATCHES_DIR / batch_id)

    # Delete previews
    _rm(PREVIEWS_DIR / batch_id)

    # Delete CSV
    if meta:
        csv_path = meta.get("csv_path")
        if csv_path:
            _rm(Path(csv_path))

    # Delete log
    delete_log(batch_id)

    # Delete metadata (last)
    delete_metadata(batch_id)

    return {"ok": True}


def auto_cleanup():
    """Delete batches older than BATCH_EXPIRE_DAYS and old previews."""
    cleanup_old_previews()
    cutoff = datetime.utcnow() - timedelta(days=BATCH_EXPIRE_DAYS)
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
