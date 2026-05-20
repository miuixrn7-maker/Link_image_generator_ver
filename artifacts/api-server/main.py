import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from urllib.parse import unquote as _unquote
from app.config import SESSION_SECRET, PORT, DATA_DIR
from app.routes.auth_routes import router as auth_router
from app.routes.batch_routes import router as batch_router
from app.routes.upload_routes import router as upload_router
from app.routes.extract_routes import router as extract_router
from app.routes.distribution_routes import router as dist_router
from app.routes.preview_routes import router as preview_router
from app.routes.image_routes import router as image_router
from app.routes.history_routes import router as history_router
from app.routes.settings_routes import router as settings_router

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


@app.on_event("startup")
async def startup():
    # Ensure data dirs exist
    for sub in ["uploads", "batches", "previews", "exports", "logs", "metadata"]:
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    # Run auto-cleanup
    try:
        from app.cleanup import auto_cleanup
        auto_cleanup()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
