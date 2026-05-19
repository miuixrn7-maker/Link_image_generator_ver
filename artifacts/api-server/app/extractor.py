import zipfile
import shutil
import io
from pathlib import Path
from typing import Callable, Optional
from PIL import Image, UnidentifiedImageError

from app.config import BATCHES_DIR, SUPPORTED_IMAGES, MAX_IMAGE_SIZE_BYTES
from app.utils import (
    fix_zip_filename, is_likely_broken_cyrillic, safe_filename,
    make_unique_filename, is_system_file
)
from app.logger_utils import log_event
from app.metadata import load_metadata, save_metadata


def _decode_zip_name(info: zipfile.ZipInfo) -> str:
    raw = info.filename
    if info.flag_bits & 0x800:
        return raw
    if is_likely_broken_cyrillic(raw):
        fixed = fix_zip_filename(raw)
        return fixed
    return raw


def extract_zip(batch_id: str, zip_path: Path, progress_cb: Optional[Callable] = None) -> dict:
    meta = load_metadata(batch_id)
    if not meta:
        return {"ok": False, "error": "Метаданные партии не найдены"}

    batch_dir = BATCHES_DIR / batch_id
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True)

    log_event(batch_id, "info", "Начало распаковки архива")

    try:
        zf = zipfile.ZipFile(zip_path, 'r')
    except zipfile.BadZipFile:
        log_event(batch_id, "error", "Архив повреждён или не является ZIP-файлом")
        return {"ok": False, "error": "Архив повреждён или не является ZIP-файлом"}
    except Exception as e:
        log_event(batch_id, "error", f"Ошибка открытия архива: {e}")
        return {"ok": False, "error": f"Ошибка открытия архива: {e}"}

    with zf:
        all_infos = zf.infolist()
        total = max(len(all_infos), 1)

        # Map: folder_path → [file_infos]
        folder_files: dict[str, list] = {}

        for i, info in enumerate(all_infos):
            if progress_cb:
                progress_cb(int(i / total * 50))  # first 50% = scanning

            decoded_name = _decode_zip_name(info)
            # Security: skip path traversal
            if '..' in decoded_name or decoded_name.startswith('/'):
                log_event(batch_id, "warning", f"Пропущен опасный путь: {decoded_name}")
                continue

            parts = decoded_name.replace('\\', '/').split('/')
            filename = parts[-1]
            if not filename or info.is_dir():
                continue

            # Skip system files
            if is_system_file(filename) or is_system_file('/'.join(parts)):
                log_event(batch_id, "warning", f"Системный файл пропущен: {decoded_name}")
                continue

            ext = Path(filename).suffix.lower()
            folder_path = '/'.join(parts[:-1]) if len(parts) > 1 else ''

            if folder_path not in folder_files:
                folder_files[folder_path] = []
            folder_files[folder_path].append((info, decoded_name, filename, ext))

        # Detect articles: folders that directly contain supported images
        article_folders: dict[str, list] = {}
        for folder_path, files in folder_files.items():
            has_images = any(ext in SUPPORTED_IMAGES for _, _, _, ext in files)
            if has_images:
                article_name = folder_path.split('/')[-1] if folder_path else 'root'
                if article_name not in article_folders:
                    article_folders[article_name] = []
                article_folders[article_name].append((folder_path, files))

        if not article_folders:
            log_event(batch_id, "error", "В архиве не найдено ни одного артикула с изображениями")
            return {"ok": False, "error": "В архиве нет папок с изображениями"}

        articles_meta = {}
        global_errors = []
        global_warnings = []

        total_articles = len(article_folders)
        article_idx = 0

        for article_name, folder_list in article_folders.items():
            if progress_cb:
                progress_cb(50 + int(article_idx / total_articles * 45))
            article_idx += 1

            article_dir = batch_dir / article_name
            article_dir.mkdir(parents=True, exist_ok=True)

            has_duplicates = len(folder_list) > 1
            source_folders = [fp for fp, _ in folder_list]
            warnings = []
            errors = []

            if has_duplicates:
                msg = "Артикул найден в нескольких папках — файлы объединены"
                warnings.append(msg)
                log_event(batch_id, "warning", msg, article=article_name)

            files_meta = []
            used_safe_names: set = set()

            for folder_path, files in folder_list:
                for info, decoded_name, filename, ext in files:
                    # Check nested subfolders (warn if file is not directly in article folder)
                    file_parts = decoded_name.replace('\\', '/').split('/')
                    folder_components = len(folder_path.split('/')) if folder_path else 0
                    if len(file_parts) > folder_components + 1:
                        nested_sub = '/'.join(file_parts[folder_components:-1])
                        warn_msg = f"Изображение во вложенной подпапке «{nested_sub}» — добавлено в артикул"
                        if warn_msg not in warnings:
                            warnings.append(warn_msg)
                            log_event(batch_id, "warning", warn_msg, article=article_name)

                    if ext not in SUPPORTED_IMAGES:
                        errors.append(f"Неподдерживаемый формат файла: {filename}")
                        log_event(batch_id, "error", f"Неподдерживаемый формат: {filename}", article=article_name)
                        continue

                    # Read file data
                    try:
                        file_data = zf.read(info.filename)
                    except Exception as e:
                        errors.append(f"Ошибка чтения файла: {filename}: {e}")
                        log_event(batch_id, "error", f"Ошибка чтения: {filename}", article=article_name)
                        continue

                    file_size = len(file_data)

                    # Check 0 byte
                    if file_size == 0:
                        errors.append(f"Файл пустой (0 байт): {filename}")
                        log_event(batch_id, "error", f"Файл пустой (0 байт): {filename}", article=article_name)
                        continue

                    # Safe filename + deduplicate
                    s_name = safe_filename(filename)
                    original_s_name = s_name
                    if s_name in used_safe_names:
                        s_name = make_unique_filename(s_name, used_safe_names)
                        dup_msg = f"Файл {original_s_name} переименован в {s_name} из-за конфликта имён"
                        warnings.append("Обнаружены одинаковые имена файлов — выполнено автоматическое переименование")
                        log_event(batch_id, "warning", dup_msg, article=article_name)
                    used_safe_names.add(s_name)

                    # Write file to disk
                    dest = article_dir / s_name
                    try:
                        with open(dest, 'wb') as f:
                            f.write(file_data)
                    except Exception as e:
                        errors.append(f"Ошибка записи файла: {s_name}: {e}")
                        continue

                    # Validate image
                    file_errors = []
                    width = height = None

                    if file_size > MAX_IMAGE_SIZE_BYTES:
                        file_errors.append("Файл больше 10 MB")
                        log_event(batch_id, "error", f"Файл больше 10 MB: {s_name}", article=article_name)

                    try:
                        with Image.open(io.BytesIO(file_data)) as img:
                            width, height = img.size
                    except UnidentifiedImageError:
                        file_errors.append("Файл повреждён или не является изображением")
                        log_event(batch_id, "error", f"Повреждённое изображение: {s_name}", article=article_name)
                    except Exception:
                        file_errors.append("Файл повреждён или не является изображением")
                        log_event(batch_id, "error", f"Ошибка открытия изображения: {s_name}", article=article_name)

                    if s_name != original_s_name:
                        log_event(batch_id, "info", f"Переименовано из-за конфликта имён: {original_s_name} → {s_name}", article=article_name)
                    elif safe_filename(filename) != filename:
                        log_event(batch_id, "info", f"Транслитерация: {filename} → {s_name}", article=article_name)

                    files_meta.append({
                        "safe_name": s_name,
                        "original_name": filename,
                        "display_name": filename,
                        "size": file_size,
                        "width": width,
                        "height": height,
                        "errors": file_errors,
                        "warnings": [],
                    })

            # Deduplicate warnings
            warnings = list(dict.fromkeys(warnings))

            articles_meta[article_name] = {
                "article": article_name,
                "source_folders": source_folders,
                "has_duplicates": has_duplicates,
                "warnings": warnings,
                "errors": errors,
                "files": files_meta,
                "assignment": {
                    "main": None,
                    "zoom": None,
                    "rest": [],
                },
            }

        meta["articles"] = articles_meta
        meta["status"] = "extracted"
        meta["stats"] = {
            "total_articles": len(articles_meta),
            "total_images": sum(len(a["files"]) for a in articles_meta.values()),
            "total_errors": sum(
                len(a["errors"]) + sum(len(f["errors"]) for f in a["files"])
                for a in articles_meta.values()
            ),
            "total_warnings": sum(len(a["warnings"]) for a in articles_meta.values()),
        }

        if progress_cb:
            progress_cb(100)

        save_metadata(batch_id, meta)
        log_event(batch_id, "info",
                  f"Распаковка завершена. Артикулов: {len(articles_meta)}, "
                  f"изображений: {meta['stats']['total_images']}")

        return {"ok": True, "articles": len(articles_meta), "images": meta['stats']['total_images']}
