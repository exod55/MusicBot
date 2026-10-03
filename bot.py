#!/usr/bin/env python3
"""
Music News Ecosystem — Telegram Bot
====================================
• Deep-link handler: t.me/Bot?start=track_{iTunesID}
• Fetches high-res 600×600 artwork + 30s preview via iTunes Lookup API
• Daily in-memory CSV backups of Supabase tables -> private Telegram channel
• Uses environment variable BOT_USERNAME dynamically
"""

import asyncio
import csv
import io
import logging
import os
from datetime import datetime
from typing import Any

import httpx
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("music-news-bot")

# Config
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BACKUP_CHANNEL_ID = int(os.environ["TELEGRAM_BACKUP_CHANNEL_ID"])
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourMusicNewsBot")

BACKUP_TZ = os.environ.get("BACKUP_TZ", "UTC")
BACKUP_HOUR = int(os.environ.get("BACKUP_HOUR", "3"))
BACKUP_MINUTE = int(os.environ.get("BACKUP_MINUTE", "0"))

BACKUP_TABLES = ["music_news", "track_metadata", "top_charts", "backup_logs", "release_radar", "top_artists"]
ITUNES_LOOKUP = "https://itunes.apple.com/lookup"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def fetch_itunes_track(track_id: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(ITUNES_LOOKUP, params={"id": track_id, "entity": "song"})
            resp.raise_for_status()
            results = resp.json().get("results") or []
            return results[0] if results else None
        except Exception as exc:
            logger.exception("iTunes lookup failed for track %s: %s", track_id, exc)
            return None


def hi_res_artwork(url: str | None) -> str | None:
    if not url:
        return None
    return url.replace("100x100bb", "600x600bb").replace("100x100", "600x600").replace("60x60bb", "600x600bb")


def format_track_caption(item: dict[str, Any]) -> str:
    title = item.get("trackName") or item.get("collectionName") or "Unknown"
    artist = item.get("artistName") or "Unknown Artist"
    album = item.get("collectionName") or "—"
    genre = item.get("primaryGenreName") or "—"
    year = (item.get("releaseDate") or "")[:4] or "—"
    explicit = "Explicit" if item.get("trackExplicitness") == "explicit" else ""
    preview = item.get("previewUrl") or ""

    lines = [
        f"<b>{_esc(title)}</b>",
        f"👤 <b>Artist:</b> {_esc(artist)}",
        f"💿 <b>Album:</b> {_esc(album)}",
        f"🎸 <b>Genre:</b> {_esc(genre)} ({year})",
    ]
    if explicit:
        lines.append(f"⚠️ {explicit}")
    if preview:
        lines.append(f'\n🎧 <a href="{preview}">30-Second Audio Preview</a>')
    return "\n".join(lines)


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return

    args = context.args or []
    payload = args[0] if args else ""

    if not payload:
        await update.effective_message.reply_text(
            f"🎵 <b>Music News Ecosystem Bot</b> (@{BOT_USERNAME})\n\n"
            "Use the Mini App track links to get high-res cover art, metadata, and 30-second audio previews.\n\n"
            f"<b>Deep-link Format:</b>\n<code>t.me/{BOT_USERNAME}?start=track_ITUNES_ID</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if payload.startswith("track_"):
        track_id = payload[6:].strip()
        if not track_id.isdigit():
            await update.effective_message.reply_text("⚠️ Invalid iTunes Track ID.")
            return

        status = await update.effective_message.reply_text("🔍 Fetching track metadata...")
        item = await fetch_itunes_track(track_id)

        if not item:
            await status.edit_text(f"❌ Track <code>{track_id}</code> not found on iTunes.", parse_mode=ParseMode.HTML)
            return

        artwork = hi_res_artwork(item.get("artworkUrl100") or item.get("artworkUrl60"))
        caption = format_track_caption(item)
        track_url = item.get("trackViewUrl")

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("View on Apple Music", url=track_url)]]) if track_url else None

        try:
            await status.delete()
            if artwork:
                await update.effective_message.reply_photo(
                    photo=artwork, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard
                )
            else:
                await update.effective_message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception as exc:
            logger.exception("Failed to deliver track card: %s", exc)


def table_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b"# Table empty\n"
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        clean = {k: (str(v) if isinstance(v, (dict, list)) else ("" if v is None else v)) for k, v in r.items()}
        writer.writerow(clean)
    return buf.getvalue().encode("utf-8")


async def fetch_table_rows(table: str) -> list[dict[str, Any]]:
    rows, offset, page_size = [], 0, 1000
    while True:
        try:
            resp = supabase.table(table).select("*").range(offset, offset + page_size - 1).execute()
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as exc:
            logger.error("Error fetching table %s: %s", table, exc)
            break
    return rows


async def run_daily_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    bot = context.bot
    tz = pytz.timezone(BACKUP_TZ)
    now = datetime.now(tz)
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")

    logger.info("Executing daily automated backup @ %s", stamp)

    for table in BACKUP_TABLES:
        try:
            rows = await fetch_table_rows(table)
            csv_bytes = table_to_csv_bytes(rows)
            filename = f"{table}_{now.strftime('%Y%m%d_%H%M%S')}.csv"
            caption = f"🗄 <b>Supabase Automated Backup</b>\n📅 {stamp}\n📋 Table: <code>{table}</code>\n📊 Rows: {len(rows)}"

            bio = io.BytesIO(csv_bytes)
            bio.name = filename

            await bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=InputFile(bio, filename=filename),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            try:
                supabase.table("backup_logs").insert(
                    {"table_name": table, "row_count": len(rows), "status": "success", "created_at": now.isoformat()}
                ).execute()
            except Exception:
                pass
        except Exception as exc:
            logger.exception("Backup job failed for table %s: %s", table, exc)


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))

    scheduler = AsyncIOScheduler(timezone=BACKUP_TZ)

    class _JobContext:
        def __init__(self, bot_instance):
            self.bot = bot_instance

    async def _scheduled_backup():
        await run_daily_backup(_JobContext(app.bot))

    scheduler.add_job(_scheduled_backup, trigger=CronTrigger(hour=BACKUP_HOUR, minute=BACKUP_MINUTE, timezone=BACKUP_TZ))
    scheduler.start()

    logger.info("Bot starting polling mode...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()