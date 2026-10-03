import os
import io
import csv
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import pytz
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import create_client, Client

# Logging
logging.basicConfig(format="%(asctime)s - [%(levelname)s] - %(message)s", level=logging.INFO)
logger = logging.getLogger("BillboardBot")

# Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourMusicNewsBot").replace("@", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID", "").strip()

# Initialize Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized.")
    except Exception as e:
        logger.error(f"Supabase init error: {e}")

# --------------------------------------------------------------------------
# Unified Server: Serves index.html to Browsers + Satisfies Render Health Check
# --------------------------------------------------------------------------
class UnifiedAppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Health check route
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK - Bot Engine Running")
            return

        # 2. Serve the 3D Billboard Mini App (index.html)
        candidate_paths = [
            os.path.join(os.path.dirname(__file__), "..", "web", "index.html"),
            os.path.join(os.path.dirname(__file__), "web", "index.html"),
            os.path.join(os.path.dirname(__file__), "index.html"),
            "web/index.html",
            "index.html"
        ]
        
        html_bytes = None
        for path in candidate_paths:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    html_bytes = f.read()
                break

        if html_bytes:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_bytes)
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is live. Please ensure web/index.html exists in your repo.")

    def log_message(self, format, *args):
        # Silence routine HTTP requests in terminal logs
        return

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), UnifiedAppHandler)
    logger.info(f"Frontend & Health server running on port {port}")
    server.serve_forever()
async def fetch_itunes_track_metadata(track_id: str) -> dict:
    url = f"https://itunes.apple.com/lookup?id={track_id}&entity=song"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                if data.get("resultCount", 0) > 0:
                    item = data["results"][0]
                    raw_art = item.get("artworkUrl100", "")
                    hires_art = raw_art.replace("100x100bb.jpg", "600x600bb.jpg")
                    return {
                        "found": True,
                        "title": item.get("trackName"),
                        "artist": item.get("artistName"),
                        "album": item.get("collectionName"),
                        "genre": item.get("primaryGenreName"),
                        "year": item.get("releaseDate", "")[:4],
                        "artwork": hires_art,
                        "preview_url": item.get("previewUrl"),
                        "view_url": item.get("trackViewUrl"),
                    }
    except Exception as e:
        logger.error(f"iTunes API lookup failed: {e}")
    return {"found": False}

# --------------------------------------------------------------------------
# Automated In-Memory CSV Supabase Backup
# --------------------------------------------------------------------------
async def perform_database_backup(context: ContextTypes.DEFAULT_TYPE):
    if not supabase or not BACKUP_CHANNEL_ID:
        logger.warning("Supabase or BACKUP_CHANNEL_ID not configured. Skipping backup.")
        return

    tables = ["music_news", "top_charts", "backup_logs"]
    current_time = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for table in tables:
        try:
            res = supabase.table(table).select("*").limit(5000).execute()
            rows = res.data
            if not rows:
                continue

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)

            byte_stream = io.BytesIO(output.getvalue().encode("utf-8"))
            filename = f"backup_{table}_{datetime.now(pytz.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            byte_stream.name = filename

            caption = (
                f"🛡️ <b>DATABASE BACKUP</b>\n\n"
                f"• <b>Table:</b> <code>{table}</code>\n"
                f"• <b>Records:</b> <code>{len(rows)}</code>\n"
                f"• <b>Timestamp:</b> <code>{current_time}</code>"
            )

            await context.bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=InputFile(byte_stream, filename=filename),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            logger.info(f"Backup sent for table: {table}")
        except Exception as e:
            logger.error(f"Backup failure on {table}: {e}")

# --------------------------------------------------------------------------
# Bot Command Handlers
# --------------------------------------------------------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    # Handle Deep Links: t.me/Bot?start=track_12345
    if args and args[0].startswith("track_"):
        track_id = args[0].replace("track_", "").strip()
        await update.message.reply_chat_action("upload_photo")

        meta = await fetch_itunes_track_metadata(track_id)
        if meta.get("found"):
            caption = (
                f"🎵 <b>{meta['title']}</b>\n"
                f"👤 <b>Artist:</b> {meta['artist']}\n"
                f"💽 <b>Album:</b> {meta['album']}\n"
                f"📅 <b>Year:</b> {meta['year']} | <b>Genre:</b> {meta['genre']}\n\n"
                f"<i>Delivered by Billboard Pulse Ecosystem</i>"
            )
            buttons = []
            if meta.get("view_url"):
                buttons.append([InlineKeyboardButton("🍎 Open in Apple Music", url=meta["view_url"])])

            await update.message.reply_photo(
                photo=meta["artwork"],
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            )
            if meta.get("preview_url"):
                await update.message.reply_audio(
                    audio=meta["preview_url"],
                    title=meta["title"],
                    performer=meta["artist"],
                    caption="⚡ <i>30-Second Master Preview</i>",
                    parse_mode=ParseMode.HTML,
                )
            return
        else:
            await update.message.reply_text(f"⚠️ Track ID <code>{track_id}</code> not found in public database.", parse_mode=ParseMode.HTML)
            return

    # Standard /start message
    msg = (
        f"🔥 <b>Billboard Pulse Ecosystem Bot</b>\n\n"
        f"Commands available:\n"
        f"• /charts - View current Top 5 Songs\n"
        f"• /news - Latest Hollywood Reporter Headlines\n"
        f"• /backup - Trigger on-demand database backup\n"
        f"• /help - Display instructions\n\n"
        f"<i>Use the Mini App Menu button to explore the 3D Billboard dashboard!</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def charts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📈 <b>Billboard Top 5 Preview</b>:\n\n"
        "1. <b>Die With A Smile</b> - Lady Gaga & Bruno Mars\n"
        "2. <b>Birds of a Feather</b> - Billie Eilish\n"
        "3. <b>Espresso</b> - Sabrina Carpenter\n"
        "4. <b>Taste</b> - Sabrina Carpenter\n"
        "5. <b>Good Luck, Babe!</b> - Chappell Roan\n\n"
        "<i>Open the Mini App to stream previews and view high-res artwork!</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📰 <b>The Hollywood Reporter • Music Wire</b>\n\n"
        "• <b>Universal & Spotify Expand AI Licensing:</b> Landmark agreement protecting artist voices and likenesses.\n\n"
        "• <b>Grammys 2026 Shift:</b> Recording Academy weighs new immersive spatial audio category.\n\n"
        "• <b>Apple Music Lossless in Automotives:</b> Cupertino strikes in-dash spatial hardware deals."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Initiating on-demand database backup...")
    await perform_database_backup(context)
    await update.message.reply_text("✅ Backup pipeline execution finished.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠️ <b>Help Menu</b>:\n"
        "Click any track inside the Mini App to send high-res covers and master audio previews directly to this chat.\n\n"
        "Available commands: /start, /charts, /news, /backup",
        parse_mode=ParseMode.HTML
    )

# --------------------------------------------------------------------------
# Main Execution
# --------------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("FATAL: TELEGRAM_TOKEN environment variable is missing.")
        return

    # Start the HTTP port listener thread so Render never times out
    threading.Thread(target=start_health_server, daemon=True).start()

    # Build bot application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("charts", charts_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("help", help_command))

    # Configure daily scheduled backup at 03:00 UTC
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(perform_database_backup, trigger="cron", hour=3, minute=0, args=[app])
    scheduler.start()

    logger.info(f"Bot @{BOT_USERNAME} initialized and polling.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
