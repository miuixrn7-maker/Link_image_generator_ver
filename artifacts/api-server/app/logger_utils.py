import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from app.config import LOGS_DIR


def _log_path(batch_id: str) -> Path:
    return LOGS_DIR / f"{batch_id}.json"


def _load_log(batch_id: str) -> list:
    path = _log_path(batch_id)
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_log(batch_id: str, entries: list):
    path = _log_path(batch_id)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=LOGS_DIR, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def log_event(batch_id: str, level: str, message: str, article: str = None):
    entries = _load_log(batch_id)
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "level": level,
        "message": message,
    }
    if article:
        entry["article"] = article
    entries.append(entry)
    _save_log(batch_id, entries)


def get_log(batch_id: str) -> list:
    return _load_log(batch_id)


def delete_log(batch_id: str):
    path = _log_path(batch_id)
    if path.exists():
        path.unlink()
