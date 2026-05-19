from pathlib import Path
from app.config import SUPPORTED_IMAGES
from app.metadata import load_metadata, save_metadata
from app.logger_utils import log_event


def _match_file(files: list, rule: dict, exclude: set = None) -> str | None:
    if exclude is None:
        exclude = set()
    candidates = [f for f in files if f["safe_name"] not in exclude and not f["errors"]]
    # also include files with only size error for assignment
    all_candidates = [f for f in files if f["safe_name"] not in exclude]

    r = rule.get("rule", "first_file")
    text = rule.get("text", "")
    extension = rule.get("extension", "")

    if r == "no_distribution":
        return None

    pool = all_candidates

    if r == "first_file":
        return pool[0]["safe_name"] if pool else None

    if r == "last_file":
        return pool[-1]["safe_name"] if pool else None

    if r == "contains_text" and text:
        matches = [f for f in pool if text.lower() in f["display_name"].lower()]
        return matches[0]["safe_name"] if matches else None

    if r == "extension" and extension:
        ext = extension if extension.startswith('.') else '.' + extension
        matches = [f for f in pool if Path(f["safe_name"]).suffix.lower() == ext.lower()]
        return matches[0]["safe_name"] if matches else None

    return None


def run_auto_distribution(batch_id: str, rules: dict) -> dict:
    meta = load_metadata(batch_id)
    if not meta:
        return {"ok": False, "error": "Метаданные не найдены"}

    articles = meta.get("articles", {})
    log_event(batch_id, "info", "Запуск автораспределения")

    main_rule = rules.get("main", {"rule": "first_file"})
    zoom_rule = rules.get("zoom", {"rule": "no_distribution"})

    results = []
    warnings_count = 0
    errors_count = 0

    for article_name, article in articles.items():
        files = article.get("files", [])
        if not files:
            continue

        all_names = set(f["safe_name"] for f in files)
        used = set()

        # Assign main
        main_file = _match_file(files, main_rule, used)
        if main_file:
            used.add(main_file)

        # Assign zoom (must differ from main)
        zoom_file = _match_file(files, zoom_rule, used)
        if zoom_file:
            used.add(zoom_file)

        # Rest = everything not used
        rest = [f["safe_name"] for f in files if f["safe_name"] not in used]

        # Fallback: if main exists, zoom empty, rest has exactly 1 image
        if main_file and not zoom_file and len(rest) == 1:
            zoom_file = rest[0]
            rest = []
            log_event(batch_id, "info",
                      "Увелич_фото заполнено автоматически по fallback-правилу.",
                      article=article_name)

        article["assignment"] = {
            "main": main_file,
            "zoom": zoom_file,
            "rest": rest,
        }

        # Count issues
        if article.get("errors"):
            errors_count += 1
        if article.get("warnings"):
            warnings_count += 1

        results.append({
            "article": article_name,
            "main": main_file,
            "zoom": zoom_file,
            "rest": rest,
        })

    meta["articles"] = articles
    meta["distribution_rules"] = rules
    meta["status"] = "distributed"
    save_metadata(batch_id, meta)

    if errors_count > 0:
        status_msg = "Автораспределение выполнено с предупреждениями"
    elif warnings_count > 0:
        status_msg = "Автораспределение выполнено с предупреждениями"
    else:
        status_msg = "Автораспределение выполнено"

    log_event(batch_id, "info", status_msg)
    return {"ok": True, "status_msg": status_msg, "results": results,
            "errors": errors_count, "warnings": warnings_count}
