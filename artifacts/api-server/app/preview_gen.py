import io
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image, UnidentifiedImageError

from app.config import BATCHES_DIR, PREVIEWS_DIR, PREVIEW_MAX_SIDE, PREVIEW_QUALITY
from app.logger_utils import log_event


def _get_quality() -> int:
    try:
        from app.settings_manager import get_setting
        q = get_setting("thumbnail_quality")
        if q is not None:
            return int(q)
    except Exception:
        pass
    return PREVIEW_QUALITY


def get_preview_path(batch_id: str, article: str, safe_name: str) -> Path:
    return PREVIEWS_DIR / batch_id / article / safe_name


def get_image_path(batch_id: str, article: str, safe_name: str) -> Path:
    return BATCHES_DIR / batch_id / article / safe_name


def generate_preview(batch_id: str, article: str, safe_name: str, force: bool = False) -> bool:
    src = get_image_path(batch_id, article, safe_name)
    dst = get_preview_path(batch_id, article, safe_name)

    if not src.exists():
        return False

    if dst.exists() and not force:
        return True

    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(src) as img:
            img = img.convert('RGB')
            w, h = img.size
            max_side = PREVIEW_MAX_SIDE
            if w > max_side or h > max_side:
                ratio = min(max_side / w, max_side / h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)
            ext = Path(safe_name).suffix.lower()
            fmt = 'JPEG'
            out_name = safe_name
            if ext == '.png':
                fmt = 'JPEG'
                out_name = Path(safe_name).stem + '.jpg'
            elif ext in ('.webp', '.jpg', '.jpeg'):
                fmt = 'JPEG'
            dst_final = dst.parent / out_name
            dst_final.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst_final, format=fmt, quality=_get_quality(), optimize=True)
        return True
    except Exception:
        return False


def get_preview_url_name(safe_name: str) -> str:
    ext = Path(safe_name).suffix.lower()
    if ext in ('.png', '.webp'):
        return Path(safe_name).stem + '.jpg'
    return safe_name


def generate_all_previews(batch_id: str, articles: dict, log: bool = True):
    count = 0
    for article_name, article in articles.items():
        for file_info in article.get("files", []):
            s_name = file_info["safe_name"]
            ok = generate_preview(batch_id, article_name, s_name)
            if ok:
                count += 1
    if log and count > 0:
        log_event(batch_id, "info", f"Превью сгенерированы: {count} шт.")


def cleanup_old_previews():
    if not PREVIEWS_DIR.exists():
        return
    expire_hours = None
    try:
        from app.settings_manager import get_setting
        expire_hours = get_setting("preview_expire_hours")
    except Exception:
        expire_hours = 24
    if expire_hours is None:
        return
    cutoff = datetime.utcnow() - timedelta(hours=int(expire_hours))
    for batch_dir in PREVIEWS_DIR.iterdir():
        if not batch_dir.is_dir():
            continue
        try:
            mtime = datetime.utcfromtimestamp(batch_dir.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(batch_dir, ignore_errors=True)
        except Exception:
            pass
