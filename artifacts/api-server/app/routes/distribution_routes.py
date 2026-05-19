from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.metadata import load_metadata
from app.distributor import run_auto_distribution
from app.logger_utils import get_log

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/batch/{batch_id}/distribute", response_class=HTMLResponse)
async def distribution_page(request: Request, batch_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    meta = load_metadata(batch_id)
    if not meta:
        return RedirectResponse(url="/", status_code=302)
    log_entries = get_log(batch_id)
    return templates.TemplateResponse(request, "auto_distribution.html", {
        "user": current_user(request),
        "batch": meta,
        "log_entries": log_entries,
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
):
    if not is_authenticated(request):
        return JSONResponse({"ok": False}, status_code=401)

    rules = {
        "main": {"rule": main_rule, "text": main_text, "extension": main_ext},
        "zoom": {"rule": zoom_rule, "text": zoom_text, "extension": zoom_ext},
    }

    result = run_auto_distribution(batch_id, rules)
    return JSONResponse(result)
