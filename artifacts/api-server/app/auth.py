from fastapi import Request
from fastapi.responses import RedirectResponse
from app.config import ADMIN_LOGIN, ADMIN_PASSWORD


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated") is True


def require_auth(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return None


def do_login(request: Request, login: str, password: str) -> bool:
    if login == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        request.session["authenticated"] = True
        request.session["user"] = login
        return True
    return False


def do_logout(request: Request):
    request.session.clear()


def current_user(request: Request) -> str:
    return request.session.get("user", "admin")
