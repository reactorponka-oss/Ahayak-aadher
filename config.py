# language: Python 3.11, file: config.py
import os

# ---- Telegram ----
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
BOT_USERNAME  = "AADHAR_FETCHER_BOT"
CHANNEL_ID    = "@AADHARSAHAYAK"
CHANNEL_URL   = "https://t.me/AADHARSAHAYAK"

# ---- Admin ----
ADMIN_ID      = 7197906650

# ---- Capsolver ----
CAPSOLVER_KEY = os.getenv("CAPSOLVER_KEY", "")

# ---- Paths ----
DB_PATH       = "sessions.db"
PDF_DIR       = "pdfs"
PROXY_FILE    = "proxies.txt"

# ---- Network / retry ----
PROXY_MAX_TRIES   = 6          # kitne proxies try karne hain ek user request pe
PAGE_TIMEOUT_MS   = 20000      # per navigation
NAV_WAIT          = "domcontentloaded"
BLOCK_RESOURCES   = True       # images/css/fonts block except captcha

# ---- Branding ----
BOT_NAME      = "Aadhaar Sahayak"
BRAND_LINE    = "🔐 Secure · ⚡ Fast · 📄 Instant PDF"
