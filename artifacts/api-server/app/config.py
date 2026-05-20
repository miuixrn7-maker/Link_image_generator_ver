import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

UPLOADS_DIR = DATA_DIR / "uploads"
BATCHES_DIR = DATA_DIR / "batches"
PREVIEWS_DIR = DATA_DIR / "previews"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = DATA_DIR / "logs"
METADATA_DIR = DATA_DIR / "metadata"

for d in [UPLOADS_DIR, BATCHES_DIR, PREVIEWS_DIR, EXPORTS_DIR, LOGS_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SESSION_SECRET = os.environ.get("SESSION_SECRET", "changeme-secret-key-32chars-min!!")
ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
BASE_URL = os.environ.get("BASE_URL", "")
PORT = int(os.environ.get("PORT", 5000))

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
SYSTEM_FILES = {".ds_store", "thumbs.db", "__macosx"}
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
PREVIEW_MAX_SIDE = 400
PREVIEW_QUALITY = 82
BATCH_EXPIRE_DAYS = 14
PREVIEW_EXPIRE_HOURS = 24

WARNING_MAX_ZIP_GB = 3
WARNING_MAX_ARTICLES = 350
WARNING_MAX_IMAGES = 900


def get_free_disk_space() -> float:
    import shutil
    try:
        usage = shutil.disk_usage(DATA_DIR)
        return usage.free / (1024 ** 3)
    except Exception:
        return 999.0
