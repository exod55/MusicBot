#!/usr/bin/env python3
"""
Music News Ecosystem — Flask Backend (no pydantic / no Rust)
============================================================
Works on Python 3.11–3.12. Avoids pydantic-core entirely.

Endpoints:
  GET  /health
  GET  /api/charts
  GET  /api/track/<itunes_id>
  GET  /api/track/<itunes_id>/preview
  GET  /api/track/<itunes_id>/preview/stream
  GET  /api/spotify/track/<spotify_id_or_url>
  POST /api/ingest/charts
  GET  /api/news
  GET  /api/releases
  GET  /api/artists
  GET  /api/db/tables
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any, Optional

import httpx
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("music-backend")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourMusicNewsBot")

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_RSS = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/{limit}/songs.json"

app = Flask(__name__)
CORS(app, origins=ALLOWED_ORIGINS.split(",") if ALLOWED_ORIGINS != "*" else "*")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client ready")
    except Exception as exc:
        logger.warning("Supabase init failed: %s", exc)
else:
    logger.warning("SUPABASE_URL / SUPABASE_KEY missing — DB routes will degrade")


def hi_res(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return (
        url.replace("100x100bb", "600x600bb")
        .replace("100x100", "600x600")
        .replace("60x60bb", "600x600bb")
    )


def itunes_lookup(itunes_id: int) -> Optional[dict[str, Any]]:
    with httpx.Client(timeout=12.0) as client:
        r = client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
        r.raise_for_status()
        results = r.json().get("results") or []
        return results[0] if results else None


def fetch_spotify_metadata(spotify_id_or_url: str) -> Optional[dict[str, Any]]:
    """Scrapes track metadata from Spotify without requiring an official API key."""
    # Extract 22-character Spotify track ID from URL or raw ID
    match = re.search(r"track/([a-zA-Z0-9]{22})", spotify_id_or_url)
    track_id = match.group(1) if match else spotify_id_or_url.strip()

    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(embed_url)
            if resp.status_code != 200:
                return None

            # Extract json resource embedded in open.spotify.com
            match = re.search(r'<script id="session" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
            if not match:
                match = re.search(r'<script id="initial-state" type="application/json">(.*?)</script>', resp.text, re.DOTALL)

            if match:
                import json
                data = json.loads(match.group(1))
                return {
                    "spotify_id": track_id,
                    "raw": data
                }

            # Fallback to oEmbed metadata standard
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            oembed_resp = client.get(oembed_url)
            if oembed_resp.status_code == 200:
                oed = oembed_resp.json()
                return {
                    "spotify_id": track_id,
                    "title": oed.get("title"),
                    "artist": oed.get("author_name"),
                    "artwork_url": oed.get("thumbnail_url"),
                    "iframe_url": oed.get("html"),
                    "source": "spotify_oembed"
                }
    except Exception as exc:
        logger.warning("Spotify metadata scraping failed for %s: %s", spotify_id_or_url, exc)
    
    return None


def item_to_card(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "itunes_id": item.get("trackId") or item.get("collectionId") or 0,
        "title": item.get("trackName") or item.get("collectionName") or "Unknown",
        "artist": item.get("artistName") or "Unknown",
        "album": item.get("collectionName"),
        "genre": item.get("primaryGenreName"),
        "year": (item.get("releaseDate") or "")[:4] or None,
        "artwork_url": hi_res(item.get("artworkUrl100") or item.get("artworkUrl60")),
        "preview_url": item.get("previewUrl"),
        "track_view_url": item.get("trackViewUrl"),
        "explicit": item.get("trackExplicitness") == "explicit",
        "duration_ms": item.get("trackTimeMillis"),
    }


def probe_preview(url: str) -> dict[str, Any]:
    result = {
        "preview_url": url,
        "is_available": False,
        "http_status": None,
        "content_type": None,
        "content_length": None,
        "can_stream": False,
    }
    if not url:
        return result
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.head(url)
            if r.status_code >= 400 or not r.headers.get("content-type"):
                r = client.get(url, headers={"Range": "bytes=0-1023"})
            result["http_status"] = r.status_code
            result["content_type"] = r.headers.get("content-type")
            cl = r.headers.get("content-length")
            result["content_length"] = int(cl) if cl and cl.isdigit() else None
            ok = 200 <= r.status_code < 400
            ct = (result["content_type"] or "").lower()
            is_audio = any(x in ct for x in ("audio", "mpeg", "aac", "octet"))
            result["is_available"] = ok and (is_audio or result["content_length"] is not None)
            result["can_stream"] = result["is_available"]
    except Exception as exc:
        logger.warning("Preview probe failed: %s", exc)
        result["http_status"] = 0
    return result


@app.get("/health")
def health():
    db_ok = False
    if supabase:
        try:
            supabase.table("backup_logs").select("id").limit(1).execute()
            db_ok = True
        except Exception:
            pass
    return jsonify({
        "status": "ok",
        "supabase": db_ok,
        "bot_username": BOT_USERNAME,
        "time": datetime.utcnow().isoformat() + "Z",
        "note": "Full music download is NOT supported. Only 30s iTunes previews.",
    })


@app.get("/")
def root():
    accept = request.headers.get("Accept", "")
    if "text/html" in accept:
        html = _load_index_html()
        if html:
            return Response(html, mimetype="text/html")
    return jsonify({
        "service": "Music News Ecosystem API (Flask)",
        "miniapp": "/app",
        "health": "/health",
        "bot_username": BOT_USERNAME,
        "important": (
            "This backend verifies and streams 30-second iTunes previews only. "
            "Full-song download is not possible with free public APIs."
        ),
    })


@app.get("/api/charts")
def get_charts():
    limit = min(max(int(request.args.get("limit", 25)), 1), 100)
    url = APPLE_RSS.format(limit=limit)
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return jsonify({"error": f"Apple RSS unreachable: {exc}"}), 502

    results = data.get("feed", {}).get("results") or []
    tracks = []
    for i, item in enumerate(results, 1):
        iid = item.get("id")
        tracks.append({
            "rank": i,
            "itunes_id": int(iid) if str(iid).isdigit() else iid,
            "title": item.get("name"),
            "artist": item.get("artistName"),
            "year": (item.get("releaseDate") or "")[:4],
            "artwork_url": hi_res(item.get("artworkUrl100")),
            "genres": item.get("genres"),
            "url": item.get("url"),
        })
    return jsonify({"source": "apple_music_rss", "count": len(tracks), "tracks": tracks})


@app.get("/api/track/<int:itunes_id>")
def get_track(itunes_id: int):
    item = itunes_lookup(itunes_id)
    if not item:
        return jsonify({"error": f"Track {itunes_id} not found"}), 404
    return jsonify(item_to_card(item))


@app.get("/api/spotify/track/<path:spotify_id>")
def get_spotify_track(spotify_id: str):
    data = fetch_spotify_metadata(spotify_id)
    if not data:
        return jsonify({"error": f"Spotify track '{spotify_id}' metadata could not be fetched"}), 404
    return jsonify(data)


@app.get("/api/track/<int:itunes_id>/preview")
def check_preview(itunes_id: int):
    item = itunes_lookup(itunes_id)
    if not item:
        return jsonify({"error": f"Track {itunes_id} not found"}), 404

    preview_url = item.get("previewUrl")
    probe = probe_preview(preview_url or "")

    persist = request.args.get("persist", "").lower() in ("1", "true", "yes")
    if persist and supabase and preview_url:
        try:
            supabase.table("preview_checks").insert({
                "itunes_id": itunes_id,
                "preview_url": preview_url,
                "is_available": probe["is_available"],
                "http_status": probe["http_status"],
                "content_type": probe["content_type"],
                "content_length": probe["content_length"],
            }).execute()
        except Exception as exc:
            logger.warning("Could not persist preview_check: %s", exc)

    return jsonify({
        "itunes_id": itunes_id,
        "preview_url": preview_url,
        "is_available": probe["is_available"],
        "http_status": probe["http_status"],
        "content_type": probe["content_type"],
        "content_length": probe["content_length"],
        "can_stream": probe["can_stream"],
        "note": "iTunes only provides 30-second previews. Full tracks are not available via free public APIs.",
    })


@app.get("/api/track/<int:itunes_id>/preview/stream")
def stream_preview(itunes_id: int):
    item = itunes_lookup(itunes_id)
    if not item or not item.get("previewUrl"):
        return jsonify({"error": "No preview available"}), 404

    url = item["previewUrl"]

    def generate():
        with httpx.stream("GET", url, timeout=30.0) as resp:
            if resp.status_code >= 400:
                return
            for chunk in resp.iter_bytes(chunk_size=8192):
                yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={
            "Content-Disposition": f'inline; filename="preview_{itunes_id}.m4a"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.get("/api/news")
def get_news():
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    if not supabase:
        return jsonify({"count": 0, "articles": [], "warning": "Supabase not configured"})
    try:
        resp = (
            supabase.table("music_news")
            .select("*")
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        return jsonify({"count": len(resp.data or []), "articles": resp.data or []})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/releases")
def get_releases():
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    if not supabase:
        return jsonify({"count": 0, "releases": [], "warning": "Supabase not configured"})
    try:
        resp = (
            supabase.table("release_radar")
            .select("*")
            .order("release_date", desc=False)
            .limit(limit)
            .execute()
        )
        return jsonify({"count": len(resp.data or []), "releases": resp.data or []})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/artists")
def get_artists():
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    if not supabase:
        return jsonify({"count": 0, "artists": [], "warning": "Supabase not configured"})
    try:
        resp = (
            supabase.table("top_artists")
            .select("*")
            .order("rank")
            .limit(limit)
            .execute()
        )
        return jsonify({"count": len(resp.data or []), "artists": resp.data or []})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/ingest/charts")
def ingest_charts():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 503

    limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    url = APPLE_RSS.format(limit=limit)
    with httpx.Client(timeout=20.0) as client:
        r = client.get(url)
        r.raise_for_status()
        results = r.json().get("feed", {}).get("results") or []

    today = date.today()
    year = today.year
    upserted = 0

    for i, item in enumerate(results, 1):
        iid = item.get("id")
        if not str(iid).isdigit():
            continue
        itunes_id = int(iid)
        artwork = hi_res(item.get("artworkUrl100"))
        title = item.get("name") or "Unknown"
        artist = item.get("artistName") or "Unknown"
        release = (item.get("releaseDate") or "")[:10] or None

        try:
            supabase.table("track_metadata").upsert(
                {
                    "itunes_id": itunes_id,
                    "title": title,
                    "artist": artist,
                    "artwork_url": artwork,
                    "release_date": release,
                    "raw_json": item,
                },
                on_conflict="itunes_id",
            ).execute()
        except Exception as exc:
            logger.warning("track_metadata upsert failed: %s", exc)

        try:
            supabase.table("top_charts").upsert(
                {
                    "chart_date": today.isoformat(),
                    "year": year,
                    "source": "apple_music_rss",
                    "rank": i,
                    "itunes_id": itunes_id,
                    "title": title,
                    "artist": artist,
                    "artwork_url": artwork,
                },
                on_conflict="chart_date,source,rank",
            ).execute()
            upserted += 1
        except Exception as exc:
            logger.warning("top_charts upsert failed: %s", exc)

    return jsonify({
        "ingested": upserted,
        "chart_date": today.isoformat(),
        "source": "apple_music_rss",
    })


@app.get("/api/db/tables")
def db_tables():
    if not supabase:
        return jsonify({"error": "Supabase not configured"}), 503

    tables = [
        "track_metadata", "top_charts", "music_news", "release_radar",
        "top_artists", "backup_logs", "preview_checks",
    ]
    out = {}
    for t in tables:
        try:
            resp = supabase.table(t).select("id", count="exact").limit(1).execute()
            out[t] = {"ok": True, "count": getattr(resp, "count", len(resp.data or []))}
        except Exception as exc:
            out[t] = {"ok": False, "error": str(exc)[:200]}
    return jsonify(out)


def _load_index_html():
    """Load index.html and inject BOT_USERNAME from environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.isfile(path):
        return None
    html = open(path, "r", encoding="utf-8").read()
    # Dynamically inject the runtime BOT_USERNAME variable into frontend
    html = re.sub(
        r'const\s+BOT_USERNAME\s*=\s*["\'].*?["\'];?',
        f'const BOT_USERNAME = "{BOT_USERNAME}";',
        html
    )
    return html


# ── Serve Mini App (same service) ─────────────────────────
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/app")
@app.get("/app/")
@app.get("/miniapp")
@app.get("/miniapp/")
def serve_miniapp():
    """Telegram Mini App — same Render service as the API."""
    html = _load_index_html()
    if html is None:
        return jsonify({"error": "index.html not found next to backend.py"}), 404
    return Response(html, mimetype="text/html")


@app.get("/favicon.ico")
def favicon():
    return "", 204

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)