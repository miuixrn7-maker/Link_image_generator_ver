import re
import unicodedata

TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}


def transliterate(text: str) -> str:
    result = []
    for ch in text:
        result.append(TRANSLIT_TABLE.get(ch, ch))
    return ''.join(result)


def safe_filename(name: str) -> str:
    stem, _, ext = name.rpartition('.')
    if not stem:
        stem = name
        ext = ''
    else:
        ext = '.' + ext.lower()
    stem = transliterate(stem)
    stem = unicodedata.normalize('NFKD', stem)
    stem = stem.encode('ascii', 'ignore').decode('ascii')
    stem = re.sub(r'[^\w\s-]', '', stem)
    stem = re.sub(r'[\s_]+', '_', stem)
    stem = re.sub(r'-+', '-', stem)
    stem = stem.strip('_- ')
    if not stem:
        stem = 'file'
    return stem + ext


def fix_zip_filename(raw: str) -> str:
    for from_enc, to_enc in [('cp437', 'cp866'), ('cp437', 'cp1251'), ('cp437', 'utf-8')]:
        try:
            fixed = raw.encode(from_enc).decode(to_enc)
            if any('\u0400' <= c <= '\u04ff' for c in fixed):
                return fixed
        except Exception:
            pass
    return raw


def is_likely_broken_cyrillic(name: str) -> bool:
    broken_chars = sum(1 for c in name if '\x80' <= c <= '\xff')
    return broken_chars > len(name) * 0.3


def make_unique_filename(base_name: str, existing: set) -> str:
    if base_name not in existing:
        return base_name
    stem, _, ext = base_name.rpartition('.')
    if not stem:
        stem = base_name
        ext = ''
    else:
        ext = '.' + ext
    candidate = f"{stem}_duplicate{ext}"
    if candidate not in existing:
        return candidate
    n = 2
    while True:
        candidate = f"{stem}_duplicate_{n}{ext}"
        if candidate not in existing:
            return candidate
        n += 1


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} МБ"


def is_system_file(name: str) -> bool:
    lower = name.lower()
    return lower in {'.ds_store', 'thumbs.db'} or '__macosx' in lower
