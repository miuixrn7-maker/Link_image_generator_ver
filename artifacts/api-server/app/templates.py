from urllib.parse import unquote
from pathlib import Path
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")


def _build() -> Jinja2Templates:
    t = Jinja2Templates(directory=_TEMPLATES_DIR)
    t.env.filters["urldecode"] = unquote
    return t


templates = _build()
