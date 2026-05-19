import json
import os
import tempfile
from pathlib import Path

from app.config import METADATA_DIR

SETTINGS_FILE = METADATA_DIR / "settings.json"

DEFAULTS: dict = {
    "batch_expire_days": 14,
    "preview_expire_hours": 24,
    "duplicate_article_behavior": "warn",
}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    except Exception:
        return dict(DEFAULTS)


def save_settings(data: dict) -> None:
    merged = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(METADATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SETTINGS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def get_setting(key: str):
    return load_settings().get(key, DEFAULTS.get(key))
