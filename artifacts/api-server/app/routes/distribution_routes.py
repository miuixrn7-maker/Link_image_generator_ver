from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.metadata import load_metadata, save_metadata
from app.distributor import run_auto_distribution
from app.logger_utils import get_log
from app.presets_manager import load_presets

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()

_DEFAULT_DIST = {
    "main_rule": "first_file",
    "main_text": "",
    "main_ext": "",
    "zoom_rule": "contains_text",
    "zoom_text": "Вид картины",
    "zoom_ext": "",
    "fallback_enabled": True,
    "selected_preset": None,
}


@router.get("/batch/{batch_id}/distribute", response_class=HTMLResponse)
async def distribution_page(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/", status_code=302)
    log_entries = get_log(batch_id)
    presets = load_presets()
    dist_settings = {**_DEFAULT_DIST, **meta.get("dist_settings", {})}
    return templates.TemplateResponse(request, "auto_distribution.html", {
        "user": current_user(request),
        "batch": meta,
        "log_entries": log_entries,
        "presets": presets,
        "dist": dist_settings,
    })


@router.post("/batch/{batch_id}/distribute")
async def run_distribution(
    request: Request,
    batch_id: str,
    main_rule: str = Form("first_file"),
    main_text: str = Form(""),
    main_ext: str = Form(""),
    zoom_rule: str = Form("contains_text"),
    zoom_text: str = Form("Вид картины"),
    zoom_ext: str = Form(""),
    fallback_enabled: str = Form("true"),
    selected_preset: str = Form(""),
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    fallback = fallback_enabled.lower() in ("true", "1", "on", "yes")

    rules = {
        "main": {"rule": main_rule, "text": main_text, "extension": main_ext},
        "zoom": {"rule": zoom_rule, "text": zoom_text, "extension": zoom_ext},
        "fallback_enabled": fallback,
    }

    # Save dist_settings to batch metadata for restoration on next visit
    meta = load_metadata(batch_id)
    if meta:
        meta["dist_settings"] = {
            "main_rule": main_rule,
            "main_text": main_text,
            "main_ext": main_ext,
            "zoom_rule": zoom_rule,
            "zoom_text": zoom_text,
            "zoom_ext": zoom_ext,
            "fallback_enabled": fallback,
            "selected_preset": selected_preset or None,
        }
        save_metadata(batch_id, meta)

    result = run_auto_distribution(batch_id, rules)
    return JSONResponse(result)
