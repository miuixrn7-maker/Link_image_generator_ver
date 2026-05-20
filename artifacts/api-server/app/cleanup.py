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


def fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} КБ"
    if size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} МБ"
    return f"{size_bytes / (1024 ** 3):.2f} ГБ"


def get_directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


def get_total_storage_usage() -> dict:
    from app.config import get_free_disk_space
    uploads = get_directory_size(UPLOADS_DIR)
    batches = get_directory_size(BATCHES_DIR)
    previews = get_directory_size(PREVIEWS_DIR)
    exports = get_directory_size(EXPORTS_DIR)
    total = uploads + batches + previews + exports
    free_gb = get_free_disk_space()
    return {
        "uploads_bytes": uploads,
        "batches_bytes": batches,
        "previews_bytes": previews,
        "exports_bytes": exports,
        "total_bytes": total,
        "uploads_fmt": fmt_size(uploads),
        "batches_fmt": fmt_size(batches),
        "previews_fmt": fmt_size(previews),
        "exports_fmt": fmt_size(exports),
        "total_fmt": fmt_size(total),
        "free_gb": round(free_gb, 1),
        "free_fmt": fmt_size(int(free_gb * (1024 ** 3))),
    }


_PROTECTED_FILES = {"settings.json", "presets.json", ".env"}


def _clear_dir_contents(path: Path, protected: set = None) -> int:
    if not path.exists():
        return 0
    count = 0
    try:
        for item in list(path.iterdir()):
            if protected and item.name in protected:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
    except Exception:
        pass
    return count


def cleanup_all_data() -> dict:
    counts = {
        "uploads": _clear_dir_contents(UPLOADS_DIR),
        "batches": _clear_dir_contents(BATCHES_DIR),
        "previews": _clear_dir_contents(PREVIEWS_DIR),
        "exports": _clear_dir_contents(EXPORTS_DIR),
        "logs": _clear_dir_contents(LOGS_DIR),
        "metadata": _clear_dir_contents(METADATA_DIR, protected=_PROTECTED_FILES),
    }
    for d in [UPLOADS_DIR, BATCHES_DIR, PREVIEWS_DIR, EXPORTS_DIR, LOGS_DIR, METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    total = sum(counts.values())
    return {"ok": True, "deleted_items": total, "counts": counts}


def cleanup_previews_only() -> dict:
    count = _clear_dir_contents(PREVIEWS_DIR)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "deleted_items": count}


def cleanup_exports_only() -> dict:
    count = _clear_dir_contents(EXPORTS_DIR)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for batch in list_all_batches():
            bid = batch.get("id")
            if not bid:
                continue
            meta = load_metadata(bid)
            if meta and meta.get("csv_path"):
                meta["csv_path"] = None
                meta["csv_filename"] = None
                if meta.get("status") == "csv_ready":
                    meta["status"] = "distributed"
                save_metadata(bid, meta)
    except Exception:
        pass
    return {"ok": True, "deleted_items": count}
