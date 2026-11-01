# language: Python 3.11, file: bot.py
"""
Aadhaar Sahayak bot — English UI. Proxy rotation, no rate-limit.
"""
import asyncio, os, re, time, sqlite3, uuid
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ConversationHandler, ContextTypes, filters)
from playwright.async_api import async_playwright
from config import (BOT_TOKEN, BOT_USERNAME, CHANNEL_ID, CHANNEL_URL, ADMIN_ID,
                    PDF_DIR, DB_PATH, PROXY_FILE, PROXY_MAX_TRIES,
                    BOT_NAME, BRAND_LINE)
from uidai import UidaiSession
from captcha_solver import solve_image_captcha
from proxy_manager import ProxyManager

GATE, MENU, ASK_ID, PROCESSING, ASK_OTP_SEND, ASK_OTP_DL = range(6)

Path(PDF_DIR).mkdir(exist_ok=True)
DB = sqlite3.connect(DB_PATH, check_same_thread=False)
DB.execute("CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY, uname TEXT, first TEXT, joined INTEGER)")
DB.execute("CREATE TABLE IF NOT EXISTS banned(uid INTEGER PRIMARY KEY, ts INTEGER)")
DB.execute("CREATE TABLE IF NOT EXISTS stats(key TEXT PRIMARY KEY, val INTEGER)")
DB.execute("INSERT OR IGNORE INTO stats VALUES('downloads', 0)")
DB.execute("INSERT OR IGNORE INTO stats VALUES('failures', 0)")
DB.commit()

PM = ProxyManager(PROXY_FILE)

def is_banned(uid: int) -> bool:
    return DB.execute("SELECT 1 FROM banned WHERE uid=?", (uid,)).fetchone() is not None

def track_user(u):
    DB.execute("INSERT OR IGNORE INTO users(uid, uname, first, joined) VALUES(?,?,?,?)",
               (u.id, u.username or "", u.first_name or "", int(time.time())))
    DB.commit()

def bump(key: str):
    DB.execute("UPDATE stats SET val = val + 1 WHERE key=?", (key,)); DB.commit()

async def member_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await ctx.bot.get_chat_member(CHANNEL_ID, update.effective_user.id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

def gate_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢  Join Official Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("🔁  Retry After Joining", callback_data="retry")],
    ])

def menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔢  Aadhaar by Number", callback_data="by_num")],
        [InlineKeyboardButton("🆔  Aadhaar by EID",    callback_data="by_eid")],
        [InlineKeyboardButton("❌  Cancel",             callback_data="cancel")],
    ])

GATE_TEXT = (
    f"👋 <b>Welcome to {BOT_NAME}</b>\n"
    f"<i>{BRAND_LINE}</i>\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "To use this bot, you must first join our official channel.\n\n"
    "1️⃣  Tap <b>Join Official Channel</b> below\n"
    "2️⃣  Join the channel, then come back\n"
    "3️⃣  Tap <b>Retry After Joining</b>\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

MENU_TEXT = (
    f"<b>{BOT_NAME}</b> — Main Menu\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "How would you like to download your e-Aadhaar?\n\n"
    "🔢  <b>Aadhaar by Number</b> — use your 12-digit Aadhaar number\n"
    "🆔  <b>Aadhaar by EID</b> — use your 28-digit Enrolment ID\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<i>Use only for your own Aadhaar, or with the holder's consent.</i>"
)

async def open_with_proxy_retry(ctx: ContextTypes.DEFAULT_TYPE, by_num: bool) -> bool:
    """Try up to PROXY_MAX_TRIES proxies. Stores sess + pw + proxy on success."""
    pw = await async_playwright().start()
    last_err = None
    for attempt in range(PROXY_MAX_TRIES):
        proxy = await PM.next()
        if proxy is None:
            last_err = "no proxies configured"
            break
        sess = UidaiSession(pw, proxy=proxy)
        try:
            await sess.open(by_num)
            PM.report_ok(proxy)
            ctx.user_data["sess"] = sess
            ctx.user_data["pw"] = pw
            ctx.user_data["proxy"] = proxy
            return True
        except Exception as e:
            PM.report_fail(proxy)
            last_err = str(e)
            try: await sess.close()
            except Exception: pass
            continue
    try: await pw.stop()
    except Exception: pass
    ctx.user_data["open_err"] = last_err or "unknown"
    return False

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user)
    if is_banned(update.effective_user.id):
        await update.message.reply_text("🚫  You have been blocked from using this bot.")
        return ConversationHandler.END
    if not await member_ok(update, ctx):
        await update.message.reply_text(GATE_TEXT, reply_markup=gate_kb(), parse_mode=ParseMode.HTML)
        return GATE
    await update.message.reply_text(MENU_TEXT, reply_markup=menu_kb(), parse_mode=ParseMode.HTML)
    return MENU

async def retry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not await member_ok(update, ctx):
        await q.edit_message_text(
            "❌  You have not joined the channel yet.\n\nPlease join first, then tap <b>Retry</b>.",
            reply_markup=gate_kb(), parse_mode=ParseMode.HTML)
        return GATE
    await q.edit_message_text(MENU_TEXT, reply_markup=menu_kb(), parse_mode=ParseMode.HTML)
    return MENU

async def pick_flow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancel":
        await q.edit_message_text("Cancelled. Send /start to begin again.")
        return ConversationHandler.END
    if is_banned(q.from_user.id):
        await q.edit_message_text("🚫  You have been blocked from using this bot.")
        return ConversationHandler.END
    by_num = q.data == "by_num"
    ctx.user_data["by_num"] = by_num
    await q.edit_message_text("⚙️  Preparing the UIDAI portal… please wait.")
    ok = await open_with_proxy_retry(ctx, by_num)
    if not ok:
        await q.edit_message_text(
            f"❌  Could not reach UIDAI with any proxy.\n"
            f"<i>{ctx.user_data.pop('open_err', '')}</i>\n\nPlease send /start to try again.",
            parse_mode=ParseMode.HTML)
        return MENU
    if by_num:
        msg = (
            "🔢  <b>Aadhaar by Number</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Please send your <b>12-digit Aadhaar number</b>.\n"
            "Spaces are allowed — the bot will remove them.\n\n"
            "<i>Example:</i> <code>1234 5678 9012</code>"
        )
    else:
        msg = (
            "🆔  <b>Aadhaar by EID</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Please send your <b>28-digit Enrolment ID (EID)</b>.\n"
            "You can find it on your Aadhaar enrolment slip.\n\n"
            "<i>Example:</i> <code>1234567890123456789012345678</code>"
        )
    await q.edit_message_text(msg, parse_mode=ParseMode.HTML)
    return ASK_ID

async def got_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().replace(" ", "").replace("-", "")
    by_num = ctx.user_data.get("by_num")
    if by_num and not re.fullmatch(r"\d{12}", txt):
        await update.message.reply_text(
            "❌  Invalid format. I need a 12-digit Aadhaar number.\nPlease send it again:",
            parse_mode=ParseMode.HTML)
        return ASK_ID
    if not by_num and not re.fullmatch(r"\d{28}", txt):
        await update.message.reply_text(
            "❌  Invalid format. I need a 28-digit EID.\nPlease send it again:",
            parse_mode=ParseMode.HTML)
        return ASK_ID
    sess: UidaiSession = ctx.user_data["sess"]
    await update.message.chat.send_action(ChatAction.TYPING)
    status = await update.message.reply_text("⚙️  Submitting your Aadhaar number…")
    try:
        await sess.fill_identifier(txt)
        cap_path = os.path.join(PDF_DIR, f"cap_{update.effective_user.id}_{uuid.uuid4().hex}.png")
        await sess.grab_captcha(cap_path)
        ctx.user_data["cap_path"] = cap_path
    except Exception as e:
        await status.edit_text(f"❌  UIDAI page error:\n<code>{e}</code>", parse_mode=ParseMode.HTML)
        await cleanup(ctx); return MENU
    await status.edit_text("🤖  Solving captcha…")
    try:
        sol = await solve_image_captcha(cap_path)
    except Exception:
        await status.edit_text("⚠️  Auto-solve failed. Please read the captcha and type it below.")
        await update.message.reply_photo(open(cap_path, "rb"),
                                         caption="Read this captcha and send the text:")
        ctx.user_data["manual_captcha"] = True
        return PROCESSING
    await status.edit_text("📨  Sending OTP…")
    try:
        await sess.submit_captcha_and_send_otp(sol)
    except Exception as e:
        await status.edit_text(
            f"❌  Captcha or OTP send failed:\n<code>{e}</code>\n\nRetrying with a fresh captcha…",
            parse_mode=ParseMode.HTML)
        cap_path = os.path.join(PDF_DIR, f"cap_{update.effective_user.id}_{uuid.uuid4().hex}.png")
        try:
            await sess.grab_captcha(cap_path)
            ctx.user_data["cap_path"] = cap_path
            sol2 = await solve_image_captcha(cap_path)
            await sess.submit_captcha_and_send_otp(sol2)
        except Exception as e2:
            await status.edit_text(f"❌  Retry also failed:\n<code>{e2}</code>", parse_mode=ParseMode.HTML)
            bump("failures")
            await cleanup(ctx); return MENU
    await status.edit_text(
        "✅  <b>OTP sent</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "A 6-digit OTP has been sent to the mobile number registered with your Aadhaar.\n\n"
        "Please send that OTP here so I can verify it.",
        parse_mode=ParseMode.HTML)
    return ASK_OTP_SEND

async def got_manual_captcha(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sess: UidaiSession = ctx.user_data["sess"]
    await update.message.chat.send_action(ChatAction.TYPING)
    status = await update.message.reply_text("📨  Sending OTP…")
    try:
        await sess.submit_captcha_and_send_otp(update.message.text.strip())
    except Exception as e:
        await status.edit_text(
            f"❌  Captcha or OTP send failed:\n<code>{e}</code>\n\nPlease send /start to try again.",
            parse_mode=ParseMode.HTML)
        bump("failures")
        await cleanup(ctx); return MENU
    ctx.user_data.pop("manual_captcha", None)
    await status.edit_text(
        "✅  <b>OTP sent</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "A 6-digit OTP has been sent to the mobile number registered with your Aadhaar.\n\n"
        "Please send that OTP here.",
        parse_mode=ParseMode.HTML)
    return ASK_OTP_SEND

async def got_otp_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    if not re.fullmatch(r"\d{6}", otp):
        await update.message.reply_text("❌  OTP must be exactly 6 digits. Please send it again.")
        return ASK_OTP_SEND
    sess: UidaiSession = ctx.user_data["sess"]
    await update.message.chat.send_action(ChatAction.TYPING)
    status = await update.message.reply_text("🔍  Verifying OTP…")
    try:
        await sess.enter_otp(otp, "send")
    except Exception as e:
        await status.edit_text(f"❌  OTP verification failed:\n<code>{e}</code>\n\nPlease send the OTP again.",
                               parse_mode=ParseMode.HTML)
        return ASK_OTP_SEND
    await status.edit_text(
        "✅  <b>OTP verified</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "A <b>second OTP</b> will now be sent to download your PDF.\n\n"
        "Please check your registered mobile and send the new OTP here.",
        parse_mode=ParseMode.HTML)
    return ASK_OTP_DL

async def got_otp_dl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    if not re.fullmatch(r"\d{6}", otp):
        await update.message.reply_text("❌  OTP must be exactly 6 digits. Please send it again.")
        return ASK_OTP_DL
    sess: UidaiSession = ctx.user_data["sess"]
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    status = await update.message.reply_text("📥  Downloading your e-Aadhaar PDF…")
    try:
        await sess.enter_otp(otp, "download")
        pdf = os.path.join(PDF_DIR, f"eaadhaar_{update.effective_user.id}_{uuid.uuid4().hex}.pdf")
        await sess.download_pdf(pdf)
    except Exception as e:
        await status.edit_text(f"❌  Download failed:\n<code>{e}</code>\n\nPlease send /start to try again.",
                               parse_mode=ParseMode.HTML)
        bump("failures")
        await cleanup(ctx); return MENU
    await status.edit_text("📤  Sending your PDF…")
    await update.message.reply_document(
        document=InputFile(open(pdf, "rb"), filename="e-Aadhaar.pdf"),
        caption=(
            "📄  <b>Your e-Aadhaar PDF</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔑  <b>Password:</b> first 4 letters of your name (CAPITALS) + birth year (YYYY)\n\n"
            "<i>Example:</i> RAHU1995\n\n"
            "Please do not share this file with anyone."
        ),
        parse_mode=ParseMode.HTML,
    )
    try: os.remove(pdf)
    except Exception: pass
    bump("downloads")
    await cleanup(ctx)
    return MENU

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cleanup(ctx)
    await update.message.reply_text("❌  Cancelled. Send /start to begin again.")
    return ConversationHandler.END

async def cleanup(ctx: ContextTypes.DEFAULT_TYPE):
    sess = ctx.user_data.pop("sess", None)
    pw   = ctx.user_data.pop("pw", None)
    if sess:
        try: await sess.close()
        except Exception: pass
    if pw:
        try: await pw.stop()
        except Exception: pass
    cap = ctx.user_data.pop("cap_path", None)
    if cap and os.path.exists(cap):
        try: os.remove(cap)
        except Exception: pass

def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, ctx)
    return wrapper

@admin_only
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total_users = DB.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_bans  = DB.execute("SELECT COUNT(*) FROM banned").fetchone()[0]
    downloads   = DB.execute("SELECT val FROM stats WHERE key='downloads'").fetchone()[0]
    failures    = DB.execute("SELECT val FROM stats WHERE key='failures'").fetchone()[0]
    ps = PM.stats()
    await update.message.reply_text(
        "<b>📊 Bot Statistics</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥  Total users: <b>{total_users}</b>\n"
        f"📥  Successful downloads: <b>{downloads}</b>\n"
        f"❌  Failures: <b>{failures}</b>\n"
        f"🚫  Banned users: <b>{total_bans}</b>\n\n"
        f"🌐  Proxies total: <b>{ps['total']}</b> · alive: <b>{ps['alive']}</b> · dead: <b>{ps['dead']}</b>",
        parse_mode=ParseMode.HTML)

@admin_only
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    text = " ".join(ctx.args)
    rows = DB.execute("SELECT uid FROM users").fetchall()
    sent = failed = 0
    status = await update.message.reply_text(f"📤  Broadcasting to {len(rows)} users…")
    for (uid,) in rows:
        try:
            await ctx.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅  Broadcast done.\nSent: {sent}\nFailed: {failed}")

@admin_only
async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /ban <user_id>"); return
    try: uid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID."); return
    DB.execute("INSERT OR IGNORE INTO banned(uid, ts) VALUES(?,?)", (uid, int(time.time())))
    DB.commit()
    await update.message.reply_text(f"🚫  User {uid} banned.")

@admin_only
async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /unban <user_id>"); return
    try: uid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID."); return
    DB.execute("DELETE FROM banned WHERE uid=?", (uid,)); DB.commit()
    await update.message.reply_text(f"✅  User {uid} unbanned.")

@admin_only
async def cmd_banlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = DB.execute("SELECT uid FROM banned ORDER BY ts DESC LIMIT 50").fetchall()
    if not rows:
        await update.message.reply_text("No banned users."); return
    lines = "\n".join(f"• <code>{u}</code>" for (u,) in rows)
    await update.message.reply_text(f"<b>🚫 Banned users</b>\n{lines}", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ps = PM.stats()
    await update.message.reply_text(
        f"<b>🌐 Proxy Pool</b>\n"
        f"Total: {ps['total']}\nAlive: {ps['alive']}\nDead: {ps['dead']}",
        parse_mode=ParseMode.HTML)

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"<b>{BOT_NAME}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "/start — open the main menu\n
