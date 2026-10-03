import os
import io
import csv
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import pytz
import httpx

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from supabase import create_client, Client

logging.basicConfig(format="%(asctime)s - [%(levelname)s] - %(message)s", level=logging.INFO)
logger = logging.getLogger("MusicSystem")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourMusicNewsBot").replace("@", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID", "").strip()

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized.")
    except Exception as e:
        logger.error(f"Supabase init error: {e}")

# --------------------------------------------------------------------------
# Spotify Tokenless Scraper Engine (SerafDosSantos Gist)
# --------------------------------------------------------------------------
class SpotifyScraper:
    def __init__(self):
        self.token = None
        self.token_expiry = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://open.spotify.com/",
        }

    async def get_token(self) -> str:
        now = datetime.now().timestamp()
        if self.token and now < self.token_expiry:
            return self.token
        url = "https://open.spotify.com/get_access_token?reason=transport&productType=web_player"
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=self.headers) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    d = r.json()
                    self.token = d.get("accessToken")
                    self.token_expiry = (d.get("accessTokenExpirationTimestampMs", 0) / 1000) - 60
                    return self.token
        except Exception as e:
            logger.error(f"Spotify token extraction error: {e}")
        return ""

    async def get_metadata(self, title: str, artist: str) -> dict:
        token = await self.get_token()
        query = f"{title} {artist}"
        if token:
            url = f"https://api.spotify.com/v1/search?q={httpx.URL(query)}&type=track&limit=1"
            headers = {**self.headers, "Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        items = r.json().get("tracks", {}).get("items", [])
                        if items:
                            t = items[0]
                            imgs = t.get("album", {}).get("images", [])
                            return {
                                "found": True,
                                "artwork": imgs[0]["url"] if imgs else "",
                                "preview_url": t.get("preview_url") or "",
                            }
            except Exception:
                pass
        return {"found": False}

spotify_engine = SpotifyScraper()

# --------------------------------------------------------------------------
# Built-In Catalog across 12 Categories
# --------------------------------------------------------------------------
CATALOG = {
    "hot_100": [
        ("A Bar Song (Tipsy)", "Shaboozey", 2024, "1.45B", "1738204892", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/4a/6c/fb/4a6cfbb8-1ce9-1f48-356c-0e6e76c12361/24UMGIM89688.rgb.jpg/600x600bb.jpg"),
        ("I Had Some Help", "Post Malone ft Morgan Wallen", 2024, "1.32B", "1744158482", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/bc/26/51/bc265147-3cf1-7b06-444d-5fcf12e432c6/24UMGIM52943.rgb.jpg/600x600bb.jpg"),
        ("Not Like Us", "Kendrick Lamar", 2024, "1.21B", "1744927237", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/71/ca/cf/71cacf21-b3b3-855d-3d23-fb91b9a957d3/24UMGIM37060.rgb.jpg/600x600bb.jpg")
    ],
    "global_top_50": [
        ("Die With A Smile", "Lady Gaga & Bruno Mars", 2024, "1.82B", "1763198083", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/4a/6c/fb/4a6cfbb8-1ce9-1f48-356c-0e6e76c12361/24UMGIM89688.rgb.jpg/600x600bb.jpg"),
        ("Birds of a Feather", "Billie Eilish", 2024, "1.74B", "1739294246", "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/0c/3d/bf/0c3dbf9b-640a-5c1a-8537-8ffb091f034d/24UMGIM39433.rgb.jpg/600x600bb.jpg")
    ],
    "grammys": [
        ("Texas Hold 'Em", "Beyoncé", 2024, "890M", "1730408497", "https://is1-ssl.mzstatic.com/image/thumb/Music122/v4/04/ea/91/04ea910c-3fc4-a095-ee02-14ebad2267ff/886444535310.jpg/600x600bb.jpg"),
        ("Fortnight", "Taylor Swift", 2024, "980M", "1739501524", "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/5e/54/22/5e542289-53e3-7be7-b08e-f6ffaa3df848/24UMGIM38271.rgb.jpg/600x600bb.jpg")
    ],
    "all_time": [
        ("Blinding Lights", "The Weeknd", 2020, "4.36B", "1499378607", "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/a4/0d/18/a40d1891-377a-e4b8-ea56-ebfa33ef80f2/20UMGIM10619.rgb.jpg/600x600bb.jpg"),
        ("Shape of You", "Ed Sheeran", 2017, "3.92B", "1193701392", "https://is1-ssl.mzstatic.com/image/thumb/Music125/v4/31/6f/30/316f30a9-25f0-62eb-b2f7-f050b100bb11/190295851286.jpg/600x600bb.jpg")
    ],
    "release_radar": [
        ("Timeless", "The Weeknd & Playboi Carti", 2024, "420M", "1771146200", "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/4a/02/1d/4a021d7b-99c0-675b-4340-9eec3d78906a/24UMGIM86105.rgb.jpg/600x600bb.jpg")
    ],
    "hiphop": [
        ("Like That", "Future & Metro Boomin", 2024, "880M", "1737520021", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/bc/26/51/bc265147-3cf1-7b06-444d-5fcf12e432c6/24UMGIM52943.rgb.jpg/600x600bb.jpg")
    ],
    "pop": [
        ("Espresso", "Sabrina Carpenter", 2024, "1.65B", "1739665427", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/58/b0/b2/58b0b2e8-5b43-4fc2-d17e-7c5efc051f47/24UMGIM39257.rgb.jpg/600x600bb.jpg")
    ],
    "rnb": [
        ("Snooze", "SZA", 2022, "1.65B", "1657829410", "https://is1-ssl.mzstatic.com/image/thumb/Music122/v4/04/ea/91/04ea910c-3fc4-a095-ee02-14ebad2267ff/886444535310.jpg/600x600bb.jpg")
    ],
    "electronic": [
        ("Strangers", "Kenya Grace", 2023, "980M", "1704192840", "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/dc/cf/92/dccf92db-b4ae-a4fa-1533-6cfc8ef0bb2e/24UMGIM78946.rgb.jpg/600x600bb.jpg")
    ],
    "latin": [
        ("Gata Only", "FloyyMenor & Cris Mj", 2024, "1.32B", "1729104920", "https://is1-ssl.mzstatic.com/image/thumb/Music221/v4/0c/3d/bf/0c3dbf9b-640a-5c1a-8537-8ffb091f034d/24UMGIM39433.rgb.jpg/600x600bb.jpg")
    ],
    "rock": [
        ("Too Sweet", "Hozier", 2024, "1.28B", "1732910490", "https://is1-ssl.mzstatic.com/image/thumb/Music211/v4/71/ca/cf/71cacf21-b3b3-855d-3d23-fb91b9a957d3/24UMGIM37060.rgb.jpg/600x600bb.jpg")
    ],
    "thr_news": [
        ("Universal & Spotify Expand AI Copyright Protections", "The Hollywood Reporter", 2026, "INDUSTRY", "news_1", "https://hollywoodreporter.com"),
        ("Grammys 2026 Shift: Recording Academy Considers Spatial Audio Field", "THR Industry Beat", 2026, "GRAMMYS", "news_2", "https://hollywoodreporter.com")
    ]
}

def seed_supabase_sync():
    """Seeds Supabase synchronously to prevent asyncio thread deadlocks."""
    if not supabase:
        return "Supabase client not configured."
    count = 0
    for cat, tracks in CATALOG.items():
        if cat == "thr_news":
            for n in tracks:
                supabase.table("music_news").upsert({
                    "title": n[0],
                    "source": n[1],
                    "summary": f"{n[0]} published by {n[1]}",
                    "url": n[5]
                }, on_conflict="title").execute()
            continue

        for i, t in enumerate(tracks):
            row = {
                "rank": i + 1,
                "track_title": t[0],
                "artist_name": t[1],
                "year": t[2],
                "streams_formatted": t[3],
                "itunes_id": t[4],
                "artwork_url": t[5],
                "chart_category": cat,
                "updated_at": datetime.now(pytz.utc).isoformat()
            }
            try:
                supabase.table("top_charts").upsert(row, on_conflict="itunes_id").execute()
                count += 1
            except Exception as e:
                logger.error(f"Upsert failed for {t[0]}: {e}")
    return f"Seeded {count} rows successfully."

# --------------------------------------------------------------------------
# HTTP Web Server & Debug Endpoint
# --------------------------------------------------------------------------
class UnifiedHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Health check
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK - Bot Engine Running")
            return

        # 2. Debug route
        if self.path == "/debug":
            status = {
                "telegram_token_set": bool(TELEGRAM_TOKEN),
                "supabase_connected": supabase is not None,
                "bot_username": BOT_USERNAME,
                "server_time": datetime.now(pytz.utc).isoformat(),
            }
            if supabase:
                try:
                    res = supabase.table("top_charts").select("id", count="exact").execute()
                    status["top_charts_count"] = res.count or len(res.data or [])
                except Exception as e:
                    status["supabase_error"] = str(e)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
            return

        # 3. CSV download
        if self.path == "/export-csv":
            if not supabase:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Supabase not connected.")
                return
            res = supabase.table("top_charts").select("*").execute()
            rows = res.data or []
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            self.send_response(200)
            self.send_header("Content-type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="charts_dump.csv"')
            self.end_headers()
            self.wfile.write(output.getvalue().encode("utf-8"))
            return

        # 4. Serve index.html (Checks disk, then falls back to built-in HTML)
        paths = [
            os.path.join(os.path.dirname(__file__), "..", "web", "index.html"),
            os.path.join(os.path.dirname(__file__), "web", "index.html"),
            "web/index.html",
            "index.html"
        ]
        html_content = None
        for p in paths:
            if os.path.exists(p):
                with open(p, "rb") as f:
                    html_content = f.read()
                break

        if not html_content:
            # Fallback embedded HTML so website NEVER fails
            html_content = b"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Billboard Pulse</title>
            <script src="https://cdn.tailwindcss.com"></script></head>
            <body class="bg-black text-white p-6 font-sans">
            <h1 class="text-3xl font-bold text-amber-400 mb-4">Billboard Pulse System Online</h1>
            <p class="text-gray-400 mb-6">Service is fully active. Check Telegram Bot or download data.</p>
            <a href="/export-csv" class="bg-amber-500 text-black px-4 py-2 rounded font-bold mr-2">Download CSV</a>
            <a href="/debug" class="bg-zinc-800 text-amber-400 px-4 py-2 rounded font-bold">System Diagnostics</a>
            </body></html>"""

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content)

    def log_message(self, format, *args):
        return

def start_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), UnifiedHandler)
    logger.info(f"Unified server bound to port {port}")
    server.serve_forever()

# --------------------------------------------------------------------------
# Telegram Handlers
# --------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0].startswith("track_"):
        track_id = args[0].replace("track_", "").strip()
        found = None
        for tracks in CATALOG.values():
            for t in tracks:
                if len(t) > 4 and t[4] == track_id:
                    found = t
                    break
        if found:
            caption = f"🎵 <b>{found[0]}</b>\n👤 <b>Artist:</b> {found[1]}\n📅 <b>Year:</b> {found[2]}"
            await update.message.reply_photo(photo=found[5], caption=caption, parse_mode=ParseMode.HTML)
            return

    await update.message.reply_text(
        f"🔥 <b>Billboard Pulse Engine Live!</b>\n\n"
        f"• /seed - Populate Supabase with 10+ lists\n"
        f"• /csv - Receive in-memory database CSV\n"
        f"• Bot Username: @{BOT_USERNAME}",
        parse_mode=ParseMode.HTML
    )

async def seed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Syncing Supabase across 12 categories...")
    msg = seed_supabase_sync()
    await update.message.reply_text(f"✅ {msg}")

async def csv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not supabase:
        await update.message.reply_text("❌ Supabase not connected.")
        return
    res = supabase.table("top_charts").select("*").execute()
    rows = res.data or []
    if not rows:
        await update.message.reply_text("⚠️ No data in database. Run /seed first.")
        return
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    bio = io.BytesIO(output.getvalue().encode("utf-8"))
    bio.name = "database_dump.csv"
    await update.message.reply_document(document=InputFile(bio), caption=f"📊 Records: {len(rows)}")

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN is missing.")
        return

    # Start HTTP server immediately
    threading.Thread(target=start_server, daemon=True).start()

    # Automatically seed database in background on startup
    threading.Thread(target=seed_supabase_sync, daemon=True).start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("seed", seed_cmd))
    app.add_handler(CommandHandler("csv", csv_cmd))

    # CRITICAL: Delete any leftover webhook to eliminate polling conflicts
    async def post_init(application: Application):
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared legacy webhooks. Polling active.")

    app.post_init = post_init
    logger.info(f"Bot @{BOT_USERNAME} starting polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
