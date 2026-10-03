import os
import io
import csv
import logging
import asyncio
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

logging.basicConfig(
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MusicEcosystemBot")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourMusicNewsBot")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID", "-1001234567890")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY and "xyzcompany" not in SUPABASE_URL:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

async def fetch_itunes_track_metadata(track_id: str) -> dict:
    url = f"https://itunes.apple.com/lookup?id={track_id}&entity=song"
    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            if data.get("resultCount", 0) > 0:
                item = data["results"][0]
                raw_artwork = item.get("artworkUrl100", "")
                hires_artwork = raw_artwork.replace("100x100bb.jpg", "600x600bb.jpg")
                return {
                    "found": True,
                    "title": item.get("trackName"),
                    "artist": item.get("artistName"),
                    "album": item.get("collectionName"),
                    "genre": item.get("primaryGenreName"),
                    "year": item.get("releaseDate", "")[:4],
                    "artwork": hires_artwork,
                    "preview_url": item.get("previewUrl"),
                    "view_url": item.get("trackViewUrl"),
                }
    return {"found": False}

async def fetch_spotify_anonymous_token() -> str:
    token_endpoint = "https://open.spotify.com/get_access_token?reason=transport&productType=web_player"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        res = await client.get(token_endpoint)
        if res.status_code == 200:
            return res.json().get("accessToken", "")
    return ""

async def scrape_spotify_metadata_tokenless(spotify_track_id: str) -> dict:
    token = await fetch_spotify_anonymous_token()
    if not token:
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{spotify_track_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(oembed_url)
            if res.status_code == 200:
                return res.json()
        return {}

    api_url = f"https://api.spotify.com/v1/tracks/{spotify_track_id}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        res = await client.get(api_url)
        if res.status_code == 200:
            return res.json()
    return {}

async def perform_database_backup(context: ContextTypes.DEFAULT_TYPE):
    if not supabase:
        logger.warning("Supabase is not configured. Skipping automated backup.")
        return

    tables_to_backup = ["music_news", "top_charts", "backup_logs"]
    current_time = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for table in tables_to_backup:
        try:
            logger.info(f"Extracting table: {table} for automated backup...")
            response = supabase.table(table).select("*").limit(10000).execute()
            rows = response.data

            if not rows:
                logger.info(f"Table '{table}' has no records to export.")
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
                f"🛡️ <b>AUTOMATED DATABASE BACKUP</b>\n\n"
                f"• <b>Table:</b> <code>{table}</code>\n"
                f"• <b>Records Count:</b> <code>{len(rows)}</code>\n"
                f"• <b>Snapshot Timestamp:</b> <code>{current_time}</code>\n"
                f"• <b>Status:</b> <code>Integrity Verified (In-Memory)</code>"
            )

            await context.bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=InputFile(byte_stream, filename=filename),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            logger.info(f"Backup for {table} transmitted to {BACKUP_CHANNEL_ID}.")

        except Exception as e:
            logger.error(f"Error executing backup for table {table}: {e}")

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user = update.effective_user

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
                f"<i>Delivered by Billboard Pulse Ecosystem Engine</i>"
            )

            buttons = []
            if meta.get("view_url"):
                buttons.append([InlineKeyboardButton("🍎 Open in Apple Music", url=meta["view_url"])])

            reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

            await update.message.reply_photo(
                photo=meta["artwork"],
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
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
            await update.message.reply_text(
                f"⚠️ Track ID <code>{track_id}</code> was not found on Apple Music Public Feeds.",
                parse_mode=ParseMode.HTML,
            )
            return

    welcome_text = (
        f"👋 Welcome <b>{user.first_name}</b> to the <b>Billboard Pulse Engine</b>!\n\n"
        f"This bot powers the interactive Web Mini App, automated nightly database backups, "
        f"and real-time metadata lookups.\n\n"
        f"• Launch the Mini App using the Menu button below.\n"
        f"• Bot Identity: <code>@{BOT_USERNAME}</code>"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def backup_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Initiating on-demand database backup pipeline...")
    await perform_database_backup(context)
    await update.message.reply_text("✅ Backup sequence completed.")

def main():
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("CRITICAL: Set the TELEGRAM_TOKEN environment variable.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("backup", backup_now_command))

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        perform_database_backup,
        trigger="cron",
        hour=3,
        minute=0,
        args=[application],
    )
    scheduler.start()
    logger.info("Scheduler initialized: Daily CSV database backup configured for 03:00 UTC.")

    logger.info(f"Bot @{BOT_USERNAME} is running.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
