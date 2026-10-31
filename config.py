# language: Python 3.11, file: config.py
import os

# ---- Telegram ----
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
BOT_USERNAME  = "AADHAR_FETCHER_BOT"
CHANNEL_ID    = "@AADHARSAHAYAK"
CHANNEL_URL   = "https://t.me/AADHARSAHAYAK"

# ---- Admin ----
ADMIN_ID      = 7197906650

# ---- Rate limit ----
MAX_PER_HOUR  = 3
COOLDOWN_SEC  = 300

# ---- Capsolver ----
CAPSOLVER_KEY = os.getenv("CAPSOLVER_KEY", "")

# ---- Paths ----
DB_PATH       = "sessions.db"
PDF_DIR       = "pdfs"

# ---- Branding ----
BOT_NAME      = "Aadhaar Sahayak"
BRAND_LINE    = "🔐 Secure · ⚡ Fast · 📄 Instant PDF"
