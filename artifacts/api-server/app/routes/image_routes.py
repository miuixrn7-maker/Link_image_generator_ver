from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import BATCHES_DIR, PREVIEWS_DIR
from app.preview_gen import get_preview_path, generate_preview, get_preview_url_name

router = APIRouter()


def _safe_path(base: Path, *parts: str) -> Path:
    resolved = base
    for part in parts:
        resolved = (resolved / part).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    return resolved


@router.get("/images/{batch_id}/{article}/{filename}")
async def serve_image(batch_id: str, article: str, filename: str):
    try:
        path = _safe_path(BATCHES_DIR, batch_id, article, filename)
    except HTTPException:
        raise
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


@router.get("/previews/{batch_id}/{article}/{filename}")
async def serve_preview(batch_id: str, article: str, filename: str):
    try:
        preview_dir = _safe_path(PREVIEWS_DIR, batch_id, article)
    except HTTPException:
        raise

    # Preview may have .jpg extension even if original was .png
    preview_name = get_preview_url_name(filename)
    preview_path = preview_dir / preview_name
    if not preview_path.exists():
        # Try to regenerate
        ok = generate_preview(batch_id, article, filename)
        if ok:
            preview_name = get_preview_url_name(filename)
            preview_path = preview_dir / preview_name
        if not preview_path.exists():
            # Fall back to original
            orig = _safe_path(BATCHES_DIR, batch_id, article, filename)
            if orig.exists():
                return FileResponse(orig)
            raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path)
