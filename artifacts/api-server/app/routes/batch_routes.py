import uuid
from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, current_user
from app.metadata import save_metadata, load_metadata

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    from app.metadata import list_all_batches
    batches = list_all_batches()[:5]
    return templates.TemplateResponse(request, "home.html", {
        "user": current_user(request),
        "recent_batches": batches,
    })


@router.get("/batch/new", response_class=HTMLResponse)
async def new_batch_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "new_batch.html", {
        "user": current_user(request),
    })


@router.post("/batch/new")
async def create_batch(request: Request, batch_name: str = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    batch_id = str(uuid.uuid4())
    date_str = datetime.utcnow().strftime("%d-%m-%Y")
    full_name = f"{batch_name}_{date_str}"
    meta = {
        "id": batch_id,
        "name": full_name,
        "display_name": batch_name,
        "created_at": datetime.utcnow().isoformat(),
        "status": "created",
        "archive_name": None,
        "archive_size": None,
        "archive_path": None,
        "articles": {},
        "distribution_rules": {
            "main": {"rule": "first_file", "text": "", "extension": ""},
            "zoom": {"rule": "contains_text", "text": "Вид картины", "extension": ""},
        },
        "stats": {"total_articles": 0, "total_images": 0, "total_errors": 0, "total_warnings": 0},
        "csv_path": None,
        "csv_filename": None,
        "csv_generated_at": None,
    }
    save_metadata(batch_id, meta)
    return RedirectResponse(url=f"/batch/{batch_id}/upload", status_code=302)
