#!/usr/bin/env python3
"""
Music News Ecosystem — Telegram Bot
====================================
Features:
  • Deep-link handler: t.me/{BOT_USERNAME}?start=track_{iTunesID}
  • Fetches high-res 600×600 artwork + 30s preview via iTunes Lookup API
  • Daily in-memory CSV backups of Supabase tables → private Telegram channel
  • APScheduler + pytz for timezone-aware cron jobs
  • Designed for Render Background Worker / Web Service

Environment variables required:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_BACKUP_CHANNEL_ID   (e.g. -1001234567890)
  BOT_USERNAME                 (optional, default "YourMusicNewsBot")
  SUPABASE_URL
  SUPABASE_KEY                 (service_role preferred for full table access)
  BACKUP_TZ                    (optional, default "UTC")
  BACKUP_HOUR                  (optional, default 3)
  BACKUP_MINUTE                (optional, default 0)
"""

from __future__ import annotations

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
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("music-news-bot")

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BACKUP_CHANNEL_ID = int(os.environ["TELEGRAM_BACKUP_CHANNEL_ID"])
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourMusicNewsBot")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

BACKUP_TZ = os.environ.get("BACKUP_TZ", "UTC")
BACKUP_HOUR = int(os.environ.get("BACKUP_HOUR", "3"))
BACKUP_MINUTE = int(os.environ.get("BACKUP_MINUTE", "0"))

# Tables to back up (order preserved in captions)
BACKUP_TABLES = [
    "music_news",
    "track_metadata",
    "top_charts",
    "backup_logs",
]

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
ITUNES_TIMEOUT = 12.0

# ─────────────────────────────────────────────────────────────
# Supabase client
# ─────────────────────────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────
# iTunes helpers
# ─────────────────────────────────────────────────────────────
async def fetch_itunes_track(track_id: str) -> dict[str, Any] | None:
    """Lookup a single track by iTunes ID. Returns first result or None."""
    async with httpx.AsyncClient(timeout=ITUNES_TIMEOUT) as client:
        try:
            resp = await client.get(
                ITUNES_LOOKUP,
                params={"id": track_id, "entity": "song"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if not results:
                return None
            return results[0]
        except Exception as exc:
            logger.exception("iTunes lookup failed for id=%s: %s", track_id, exc)
            return None


def hi_res_artwork(url: str | None) -> str | None:
    """Upgrade artworkUrl100 → 600x600bb.jpg."""
    if not url:
        return None
    return (
        url.replace("100x100bb", "600x600bb")
        .replace("100x100", "600x600")
        .replace("60x60bb", "600x600bb")
    )


def format_track_caption(item: dict[str, Any]) -> str:
    """Build a clean HTML caption for the metadata card."""
    title = item.get("trackName") or item.get("collectionName") or "Unknown"
    artist = item.get("artistName") or "Unknown Artist"
    album = item.get("collectionName") or "—"
    genre = item.get("primaryGenreName") or "—"
    year = (item.get("releaseDate") or "")[:4] or "—"
    track_num = item.get("trackNumber")
    disc = item.get("discNumber")
    explicit = "🅴 Explicit" if item.get("trackExplicitness") == "explicit" else ""
    preview = item.get("previewUrl") or ""

    lines = [
        f"<b>{_esc(title)}</b>",
        f"👤 {_esc(artist)}",
        f"💿 {_esc(album)}",
        f"🎸 {_esc(genre)} · {year}",
    ]
    if track_num:
        disc_str = f"Disc {disc} · " if disc and disc > 1 else ""
        lines.append(f"🔢 {disc_str}Track {track_num}")
    if explicit:
        lines.append(explicit)
    if preview:
        lines.append(f'\n🎧 <a href="{preview}">30-second preview</a>')

    return "\n".join(lines)


def _esc(text: str) -> str:
    """Minimal HTML escape for Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ─────────────────────────────────────────────────────────────
# Deep-link /start handler
# ─────────────────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and deep-links of the form track_{iTunesID}."""
    if not update.effective_message or not update.effective_user:
        return

    args = context.args or []
    payload = args[0] if args else ""

    # Plain /start
    if not payload:
        await update.effective_message.reply_text(
            "🎵 <b>Music News Ecosystem</b>\n\n"
            "Open a track card in the Mini App and tap <b>Open in Telegram Bot</b> "
            "to receive a rich metadata card with high-res artwork and a 30-second preview.\n\n"
            "Deep-link format:\n"
            f"<code>t.me/{BOT_USERNAME}?start=track_ITUNES_ID</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Deep-link: track_{id}
    if payload.startswith("track_"):
        track_id = payload[6:].strip()
        if not track_id.isdigit():
            await update.effective_message.reply_text(
                "⚠️ Invalid track ID. Expected numeric iTunes identifier."
            )
            return

        status = await update.effective_message.reply_text("🔍 Fetching track metadata…")
        item = await fetch_itunes_track(track_id)

        if not item:
            await status.edit_text(
                f"❌ Track <code>{track_id}</code> not found on iTunes.",
                parse_mode=ParseMode.HTML,
            )
            return

        artwork = hi_res_artwork(item.get("artworkUrl100") or item.get("artworkUrl60"))
        caption = format_track_caption(item)

        # Optional “Open in Apple Music” button
        track_view_url = item.get("trackViewUrl")
        keyboard = None
        if track_view_url:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open in Apple Music", url=track_view_url)]]
            )

        try:
            if artwork:
                await status.delete()
                await update.effective_message.reply_photo(
                    photo=artwork,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            else:
                await status.edit_text(
                    caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=False,
                )
        except Exception as exc:
            logger.exception("Failed to send track card: %s", exc)
            await status.edit_text(
                f"⚠️ Metadata retrieved but media send failed.\n\n{caption}",
                parse_mode=ParseMode.HTML,
            )
        return

    # Unknown payload
    await update.effective_message.reply_text(
        f"Received payload <code>{_esc(payload)}</code>. "
        "Supported deep-link: <code>track_ITUNES_ID</code>",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
# In-memory CSV backup pipeline
# ─────────────────────────────────────────────────────────────
def table_to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Serialize a list of dicts to CSV bytes (in-memory)."""
    if not rows:
        buf = io.StringIO()
        buf.write("# empty table\n")
        return buf.getvalue().encode("utf-8")

    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                clean[k] = str(v)
            elif v is None:
                clean[k] = ""
            else:
                clean[k] = v
        writer.writerow(clean)
    return buf.getvalue().encode("utf-8")


async def fetch_table(table: str) -> list[dict[str, Any]]:
    """Pull an entire table from Supabase (paginated for safety)."""
    all_rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0

    while True:
        try:
            resp = (
                supabase.table(table)
                .select("*")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        except Exception as exc:
            logger.error("Failed to fetch table %s (offset %s): %s", table, offset, exc)
            break

    return all_rows


async def run_daily_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    bot = context.bot
    tz = pytz.timezone(BACKUP_TZ)
    now = datetime.now(tz)
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")

    logger.info("Starting daily backup @ %s", stamp)

    for table in BACKUP_TABLES:
        try:
            rows = await fetch_table(table)
            csv_bytes = table_to_csv_bytes(rows)
            filename = f"{table}_{now.strftime('%Y%m%d_%H%M%S')}.csv"

            caption = (
                f"🗄 <b>Supabase Backup</b>\n"
                f"📅 {stamp}\n"
                f"📋 Table: <code>{table}</code>\n"
                f"📊 Rows: {len(rows)}"
            )

            bio = io.BytesIO(csv_bytes)
            bio.name = filename

            await bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=InputFile(bio, filename=filename),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            logger.info("Backed up %s (%d rows)", table, len(rows))

            try:
                supabase.table("backup_logs").insert(
                    {
                        "table_name": table,
                        "row_count": len(rows),
                        "status": "success",
                        "created_at": now.isoformat(),
                    }
                ).execute()
            except Exception:
                pass

        except Exception as exc:
            logger.exception("Backup failed for table %s: %s", table, exc)
            try:
                await bot.send_message(
                    chat_id=BACKUP_CHANNEL_ID,
                    text=(
                        f"⚠️ <b>Backup failed</b>\n"
                        f"📅 {stamp}\n"
                        f"📋 Table: <code>{table}</code>\n"
                        f"❌ {_esc(str(exc)[:300])}"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────
# Admin / utility commands
# ─────────────────────────────────────────────────────────────
async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    await update.effective_message.reply_text("⏳ Running backup now…")
    await run_daily_backup(context)
    await update.effective_message.reply_text("✅ Backup job finished. Check the private channel.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "<b>Music News Bot</b>\n\n"
        "• Open the Mini App and tap <b>Open in Telegram Bot</b> on any track.\n"
        "• Deep-link: <code>/start track_ITUNES_ID</code>\n"
        "• Admins: <code>/backup_now</code> forces an immediate CSV backup.",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────────
# Application bootstrap
# ─────────────────────────────────────────────────────────────
def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("backup_now", backup_now))

    scheduler = AsyncIOScheduler(timezone=BACKUP_TZ)

    class _JobContext:
        def __init__(self, bot):
            self.bot = bot

    async def _scheduled_backup():
        await run_daily_backup(_JobContext(app.bot))

    scheduler.add_job(
        _scheduled_backup,
        trigger=CronTrigger(
            hour=BACKUP_HOUR,
            minute=BACKUP_MINUTE,
            timezone=BACKUP_TZ,
        ),
        id="daily_supabase_backup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — daily backup at %02d:%02d %s",
        BACKUP_HOUR,
        BACKUP_MINUTE,
        BACKUP_TZ,
    )

    logger.info("Bot starting (polling)…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()