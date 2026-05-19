import json
import os
import tempfile

from app.config import METADATA_DIR

PRESETS_FILE = METADATA_DIR / "presets.json"

DEFAULT_PRESETS: list = [
    {
        "name": "Картины",
        "main_rule": "first_file",
        "main_text": "",
        "main_ext": "",
        "zoom_rule": "contains_text",
        "zoom_text": "Вид картины",
        "zoom_ext": "",
        "fallback_enabled": True,
    },
    {
        "name": "Мозаика",
        "main_rule": "first_file",
        "main_text": "",
        "main_ext": "",
        "zoom_rule": "last_file",
        "zoom_text": "",
        "zoom_ext": "",
        "fallback_enabled": True,
    },
    {
        "name": "Интерьерка",
        "main_rule": "first_file",
        "main_text": "",
        "main_ext": "",
        "zoom_rule": "no_distribution",
        "zoom_text": "",
        "zoom_ext": "",
        "fallback_enabled": False,
    },
]


def _write_presets(presets: list) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(METADATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, PRESETS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def load_presets() -> list:
    if not PRESETS_FILE.exists():
        _write_presets(DEFAULT_PRESETS)
        return list(DEFAULT_PRESETS)
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            _write_presets(DEFAULT_PRESETS)
            return list(DEFAULT_PRESETS)
        return data
    except Exception:
        return list(DEFAULT_PRESETS)


def get_preset(name: str) -> dict | None:
    for p in load_presets():
        if p.get("name") == name:
            return p
    return None


def add_or_update_preset(preset: dict) -> None:
    presets = load_presets()
    for i, p in enumerate(presets):
        if p.get("name") == preset.get("name"):
            presets[i] = preset
            _write_presets(presets)
            return
    presets.append(preset)
    _write_presets(presets)


def delete_preset(name: str) -> dict:
    presets = load_presets()
    if len(presets) <= 1:
        return {"ok": False, "error": "Нельзя удалить последний пресет"}
    new_presets = [p for p in presets if p.get("name") != name]
    if len(new_presets) == len(presets):
        return {"ok": False, "error": "Пресет не найден"}
    _write_presets(new_presets)
    return {"ok": True}
