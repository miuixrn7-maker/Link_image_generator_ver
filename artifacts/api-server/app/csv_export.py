import csv
import io
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from app.config import EXPORTS_DIR, BASE_URL
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event
from app.preview_gen import get_image_path


def _resolve_base_url(base_url: str) -> str:
    if base_url:
        return base_url.rstrip('/')
    domains = os.environ.get("REPLIT_DOMAINS", "")
    if domains:
        first = domains.split(",")[0].strip()
        return f"https://{first}"
    dev = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if dev:
        return f"https://{dev}"
    return ""


def build_image_url(batch_id: str, article: str, safe_name: str, base_url: str) -> str:
    encoded_article = quote(article, safe='')
    encoded_name = quote(safe_name, safe='')
    return f"{base_url}/images/{batch_id}/{encoded_article}/{encoded_name}"


def generate_csv(batch_id: str, base_url: str) -> dict:
    meta = load_metadata(batch_id)
    if not meta:
        return {"ok": False, "error": "Метаданные не найдены"}

    articles = meta.get("articles", {})
    batch_name = meta.get("name", batch_id)
    csv_filename = f"{batch_name}.csv"
    csv_path = EXPORTS_DIR / csv_filename

    resolved_base = _resolve_base_url(base_url)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow(["Артикул", "Путь", "Главная", "Увелич_фото", "Остальные_фото", "Ошибки"])

    rows_written = 0
    for article_id, article in sorted(articles.items()):
        assignment = article.get("assignment", {})
        display_article = article.get("display_article", article_id)
        # "Путь" column: use source_path (V2) or fall back to source_folders (V1 batches)
        source_path = article.get("source_path")
        if source_path is None:
            source_folders = article.get("source_folders", [])
            source_path = "; ".join(source_folders) if source_folders else ""

        main_file = assignment.get("main")
        zoom_file = assignment.get("zoom")
        rest_files = list(dict.fromkeys(f for f in assignment.get("rest", []) if f))

        main_url = build_image_url(batch_id, article_id, main_file, resolved_base) if main_file else ""
        zoom_url = build_image_url(batch_id, article_id, zoom_file, resolved_base) if zoom_file else ""
        rest_urls = ";".join(
            build_image_url(batch_id, article_id, f, resolved_base) for f in rest_files
        )

        article_errors = article.get("errors", [])
        file_errors = [
            err
            for f in article.get("files", [])
            for err in f.get("errors", [])
        ]
        all_errors = article_errors + file_errors
        errors_cell = "; ".join(all_errors) if all_errors else ""

        writer.writerow([display_article, source_path, main_url, zoom_url, rest_urls, errors_cell])
        rows_written += 1

    csv_content = '\ufeff' + output.getvalue()

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        f.write(csv_content)

    meta["csv_path"] = str(csv_path)
    meta["csv_filename"] = csv_filename
    meta["status"] = "csv_ready"
    meta["csv_generated_at"] = datetime.utcnow().isoformat()
    save_metadata(batch_id, meta)

    log_event(batch_id, "info", f"CSV сгенерирован: {csv_filename}, строк: {rows_written}")
    return {"ok": True, "filename": csv_filename, "rows": rows_written}


def delete_csv(batch_id: str):
    meta = load_metadata(batch_id)
    if not meta:
        return
    csv_path = meta.get("csv_path")
    if csv_path:
        p = Path(csv_path)
        if p.exists():
            p.unlink()
