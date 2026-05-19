from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from pathlib import Path

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
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    batch_days = None if batch_expire_days == "never" else int(batch_expire_days)
    preview_hours = None if preview_expire_hours == "never" else int(preview_expire_hours)
    thumb_q = int(thumbnail_quality) if thumbnail_quality.isdigit() else 82

    save_settings({
        "batch_expire_days": batch_days,
        "preview_expire_hours": preview_hours,
        "thumbnail_quality": thumb_q,
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
