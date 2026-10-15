import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file if it exists
load_dotenv(BASE_DIR / ".env")

# Bot Tokens - strictly loaded from environment variables
CUSTOMER_BOT_TOKEN = os.getenv("CUSTOMER_BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()

# Authorized Admin Telegram User IDs
# Whitelist defaults to specified production admin IDs: 742368838 and 8798202536
DEFAULT_ADMIN_IDS = {742368838, 8798202536}

admin_ids_env = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = set(DEFAULT_ADMIN_IDS)

if admin_ids_env:
    for aid in admin_ids_env.split(","):
        aid = aid.strip()
        if aid.isdigit():
            ADMIN_USER_IDS.add(int(aid))

admin_id_1 = os.getenv("ADMIN_USER_ID_1", "").strip()
if admin_id_1.isdigit():
    ADMIN_USER_IDS.add(int(admin_id_1))

admin_id_2 = os.getenv("ADMIN_USER_ID_2", "").strip()
if admin_id_2.isdigit():
    ADMIN_USER_IDS.add(int(admin_id_2))

# Channel Settings
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@iSwitch0").strip()

# MTProto API Credentials (optional for client-side authorized Telegram scraping)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "").strip()

# Database & Storage
DATA_DIR_ENV = os.getenv("DATA_DIR", "").strip()
if DATA_DIR_ENV:
    DATA_DIR = Path(DATA_DIR_ENV)
else:
    DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "iswitch.db")))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

RECEIPTS_DIR = DATA_DIR / "receipts"
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

EXPORTS_DIR = DATA_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Webhook / Server Settings
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_PORT = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8000")))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "iswitch_webhook_secret_key")

# Defaults
DEFAULT_CURRENCY = "ETB"
DEFAULT_DELIVERY_FEE = 150.0
MAX_RECEIPT_SIZE_MB = 10
ALLOWED_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
