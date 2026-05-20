from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.auth import is_authenticated, current_user
from app.settings_manager import load_settings, save_settings, DEFAULTS
from app.presets_manager import load_presets, add_or_update_preset, delete_preset

from app.templates import templates
router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    settings = load_settings()
    return templates.TemplateResponse(request, "settings.html", {
        "user": current_user(request),
        "settings": settings,
        "saved": request.query_params.get("saved"),
        "reset_done": request.query_params.get("reset"),
    })


@router.post("/settings/save")
async def save_settings_route(
    request: Request,
    batch_expire_days: str = Form("14"),
    preview_expire_hours: str = Form("24"),
    thumbnail_quality: str = Form("82"),
    vps_total_gb: str = Form("80"),
    warn_free_gb: str = Form("15"),
    warn_large_archive: Optional[str] = Form(None),
    warn_zip_gb: str = Form("3"),
    warn_max_articles: str = Form("350"),
    warn_max_images: str = Form("900"),
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    def _int(s, default):
        try:
            return int(s)
        except Exception:
            return default

    batch_days = None if batch_expire_days == "never" else _int(batch_expire_days, 14)
    preview_hours = None if preview_expire_hours == "never" else _int(preview_expire_hours, 24)

    save_settings({
        "batch_expire_days": batch_days,
        "preview_expire_hours": preview_hours,
        "thumbnail_quality": _int(thumbnail_quality, 82),
        "vps_total_gb": _int(vps_total_gb, 80),
        "warn_free_gb": _int(warn_free_gb, 15),
        "warn_large_archive": warn_large_archive is not None,
        "warn_zip_gb": _int(warn_zip_gb, 3),
        "warn_max_articles": _int(warn_max_articles, 350),
        "warn_max_images": _int(warn_max_images, 900),
    })
    return RedirectResponse(url="/settings?saved=1", status_code=302)


@router.post("/settings/reset")
async def reset_settings_route(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    save_settings(dict(DEFAULTS))
    return RedirectResponse(url="/settings?reset=1", status_code=302)


@router.get("/api/presets")
async def get_presets_api(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    return JSONResponse({"ok": True, "presets": load_presets()})


@router.post("/api/presets/save")
async def save_preset_api(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await request.json()
        name = (data.get("name") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "Название пресета не может быть пустым"})
        existing = [p for p in load_presets() if p.get("name") == name]
        preset = {
            "name": name,
            "main_rule": data.get("main_rule", "first_file"),
            "main_text": data.get("main_text", ""),
            "main_ext": data.get("main_ext", ""),
            "zoom_rule": data.get("zoom_rule", "contains_text"),
            "zoom_text": data.get("zoom_text", ""),
            "zoom_ext": data.get("zoom_ext", ""),
            "fallback_enabled": bool(data.get("fallback_enabled", True)),
        }
        add_or_update_preset(preset)
        return JSONResponse({"ok": True, "existed": bool(existing)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/api/presets/delete")
async def delete_preset_api(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)
    try:
        data = await request.json()
        name = data.get("name", "")
        result = delete_preset(name)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
