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


def is_likely_broken_cyrillic(name: str) -> bool:
    """Detect strings that contain garbled non-UTF8 text.

    Covers two cases:
    1. Python decoded bytes as CP437 → chars in \\x80-\\xff range.
    2. Python decoded bytes as UTF-8 with surrogateescape → surrogate chars
       in range \\udc80-\\udcff (raw bytes 0x80-0xFF smuggled through).
    """
    broken = sum(
        1 for c in name
        if ('\x80' <= c <= '\xff') or ('\udc80' <= c <= '\udcff')
    )
    return broken > len(name) * 0.3


def fix_zip_filename(raw: str) -> str:
    """Attempt to recover the correct filename from a mis-decoded ZIP entry.

    Handles two origins:
    A. Python decoded the raw bytes as CP437 (standard ZIP without UTF-8 flag):
       re-encode as CP437 to recover bytes, then try CP866 / CP1251.
    B. Python decoded the raw bytes as UTF-8 with surrogateescape (UTF-8 flag
       set, but bytes were actually CP866/CP1251):
       recover raw bytes via surrogateescape, then decode as CP866 / CP1251.
    """
    # Case B: surrogate characters present → recover raw bytes via surrogateescape
    if any('\udc80' <= c <= '\udcff' for c in raw):
        try:
            raw_bytes = raw.encode('utf-8', 'surrogateescape')
            for enc in ('cp866', 'cp1251'):
                try:
                    fixed = raw_bytes.decode(enc)
                    if any('\u0400' <= c <= '\u04ff' for c in fixed):
                        return fixed
                except Exception:
                    pass
        except Exception:
            pass

    # Case A: bytes were decoded as CP437 → re-encode to recover original bytes
    for from_enc, to_enc in [('cp437', 'cp866'), ('cp437', 'cp1251'), ('cp437', 'utf-8')]:
        try:
            fixed = raw.encode(from_enc).decode(to_enc)
            if any('\u0400' <= c <= '\u04ff' for c in fixed):
                return fixed
        except Exception:
            pass

    return raw


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
