from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.auth import is_authenticated, do_login, do_logout, current_user

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent.parent / "templates"))
router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, login: str = Form(...), password: str = Form(...)):
    if do_login(request, login, password):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": "Неверный логин или пароль"})


@router.get("/logout")
async def logout(request: Request):
    do_logout(request)
    return RedirectResponse(url="/login", status_code=302)
