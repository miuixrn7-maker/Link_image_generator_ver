import json
import os
import tempfile
from pathlib import Path
from typing import Optional
from app.config import METADATA_DIR


def _meta_path(batch_id: str) -> Path:
    return METADATA_DIR / f"{batch_id}.json"


def load_metadata(batch_id: str) -> Optional[dict]:
    path = _meta_path(batch_id)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_metadata(batch_id: str, data: dict) -> bool:
    path = _meta_path(batch_id)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=METADATA_DIR, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return False


def list_all_batches() -> list:
    batches = []
    for p in METADATA_DIR.glob('*.json'):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            batches.append(data)
        except Exception:
            continue
    batches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return batches


def delete_metadata(batch_id: str):
    path = _meta_path(batch_id)
    if path.exists():
        path.unlink()
