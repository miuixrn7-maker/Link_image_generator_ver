import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from urllib.parse import unquote as _unquote
from app.config import SESSION_SECRET, PORT, DATA_DIR, BASE_URL, get_free_disk_space
from app.routes.auth_routes import router as auth_router
from app.routes.batch_routes import router as batch_router
from app.routes.upload_routes import router as upload_router
from app.routes.extract_routes import router as extract_router
from app.routes.distribution_routes import router as dist_router
from app.routes.preview_routes import router as preview_router
from app.routes.image_routes import router as image_router
from app.routes.history_routes import router as history_router
from app.routes.settings_routes import router as settings_router
from app.routes.guide_routes import router as guide_router

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Генератор прямых ссылок")


class NoIndexMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response


app.add_middleware(NoIndexMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="session",
    max_age=86400 * 7,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt():
    return "User-agent: *\nDisallow: /\n"


app.include_router(auth_router)
app.include_router(batch_router)
app.include_router(upload_router)
app.include_router(extract_router)
app.include_router(dist_router)
app.include_router(preview_router)
app.include_router(image_router)
app.include_router(history_router)
app.include_router(settings_router)
app.include_router(guide_router)


@app.on_event("startup")
async def startup():
    subs = ["uploads", "batches", "previews", "exports", "logs", "metadata"]
    for sub in subs:
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    try:
        from app.cleanup import auto_cleanup
        auto_cleanup()
    except Exception:
        pass
    _print_startup_diagnostics(subs)


def _print_startup_diagnostics(subs: list):
    free_gb = get_free_disk_space()
    url = BASE_URL or os.environ.get("REPLIT_DEV_DOMAIN", "(не задан)")
    lines = [
        "=" * 52,
        "  Генератор прямых ссылок — запуск",
        f"  BASE_URL     : {url}",
        f"  Диск свободно: {free_gb:.1f} ГБ",
        "  Папки данных :",
    ]
    for sub in subs:
        d = DATA_DIR / sub
        status = "OK" if (d.exists() and os.access(d, os.W_OK)) else "ERR"
        lines.append(f"    {status}  {sub}/")
    lines.append("=" * 52)
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
