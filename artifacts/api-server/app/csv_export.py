import csv
import io
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from app.config import EXPORTS_DIR, BASE_URL
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event
from app.preview_gen import get_image_path


def build_image_url(batch_id: str, article: str, safe_name: str, base_url: str) -> str:
    encoded = quote(safe_name, safe='')
    return f"{base_url}/images/{batch_id}/{article}/{encoded}"


def generate_csv(batch_id: str, base_url: str) -> dict:
    meta = load_metadata(batch_id)
    if not meta:
        return {"ok": False, "error": "Метаданные не найдены"}

    articles = meta.get("articles", {})
    batch_name = meta.get("name", batch_id)
    csv_filename = f"{batch_name}.csv"
    csv_path = EXPORTS_DIR / csv_filename

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow(["Артикул", "Путь", "Главная", "Увелич_фото", "Остальные_фото"])

    rows_written = 0
    for article_name, article in sorted(articles.items()):
        assignment = article.get("assignment", {})
        source_folders = article.get("source_folders", [])
        path_str = "; ".join(source_folders) if source_folders else ""

        main_file = assignment.get("main")
        zoom_file = assignment.get("zoom")
        rest_files = assignment.get("rest", [])

        main_url = build_image_url(batch_id, article_name, main_file, base_url) if main_file else ""
        zoom_url = build_image_url(batch_id, article_name, zoom_file, base_url) if zoom_file else ""
        rest_urls = ";".join(
            build_image_url(batch_id, article_name, f, base_url) for f in rest_files
        )

        writer.writerow([article_name, path_str, main_url, zoom_url, rest_urls])
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
