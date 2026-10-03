#!/usr/bin/env python3
"""
Music News Ecosystem — Flask Backend
Serves Mini App + API on the same Render Web Service.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

import httpx
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("music-backend")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "YourMusicNewsBot")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_RSS = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/{limit}/songs.json"

app = Flask(__name__)
CORS(app, origins=ALLOWED_ORIGINS.split(",") if ALLOWED_ORIGINS != "*" else "*")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase ready")
    except Exception as exc:
        logger.warning("Supabase init failed: %s", exc)


def hi_res(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return (
        url.replace("100x100bb", "600x600bb")
        .replace("100x100", "600x600")
        .replace("60x60bb", "600x600bb")
    )


def _load_index_html() -> Optional[str]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.isfile(path):
        return None
    html = open(path, "r", encoding="utf-8").read()
    html = html.replace('const BOT_USERNAME = "YourMusicNewsBot"', f'const BOT_USERNAME = "{BOT_USERNAME}"')
    html = html.replace("const BOT_USERNAME = 'YourMusicNewsBot'", f'const BOT_USERNAME = "{BOT_USERNAME}"')
    return html


# ── Mini App (fixes Not Found on / and /app) ───────────────

@app.get("/")
def root():
    accept = request.headers.get("Accept", "")
    if "text/html" in accept or request.args.get("app"):
        html = _load_index_html()
        if html:
            return Response(html, mimetype="text/html")
    return jsonify({
        "service": "Music News Ecosystem API",
        "miniapp": "/app",
        "health": "/health",
        "charts": "/api/charts?limit=100",
        "bot_username": BOT_USERNAME,
        "note": "Only 30s iTunes previews — no full-track download",
    })


@app.get("/app")
@app.get("/app/")
@app.get("/miniapp")
@app.get("/miniapp/")
def serve_miniapp():
    html = _load_index_html()
    if not html:
        return jsonify({"error": "index.html missing next to backend.py on the server"}), 404
    return Response(html, mimetype="text/html")


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
    })


# ── Charts ─────────────────────────────────────────────────

@app.get("/api/charts")
def get_charts():
    limit = min(max(int(request.args.get("limit", 100)), 1), 100)
    url = APPLE_RSS.format(limit=limit)
    try:
        with httpx.Client(timeout=20.0) as client:
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
            "id": iid,
            "title": item.get("name"),
            "name": item.get("name"),
            "artist": item.get("artistName"),
            "artistName": item.get("artistName"),
            "year": (item.get("releaseDate") or "")[:4],
            "releaseDate": item.get("releaseDate"),
            "artwork_url": hi_res(item.get("artworkUrl100")),
            "artworkUrl100": item.get("artworkUrl100"),
            "genres": item.get("genres"),
            "url": item.get("url"),
        })
    return jsonify({"source": "apple_music_rss", "count": len(tracks), "tracks": tracks, "feed": {"results": results}})


@app.get("/api/track/<int:itunes_id>")
def get_track(itunes_id: int):
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
            r.raise_for_status()
            results = r.json().get("results") or []
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    if not results:
        return jsonify({"error": "not found"}), 404
    item = results[0]
    return jsonify({
        "itunes_id": item.get("trackId"),
        "title": item.get("trackName"),
        "artist": item.get("artistName"),
        "album": item.get("collectionName"),
        "genre": item.get("primaryGenreName"),
        "year": (item.get("releaseDate") or "")[:4],
        "artwork_url": hi_res(item.get("artworkUrl100")),
        "preview_url": item.get("previewUrl"),
        "track_view_url": item.get("trackViewUrl"),
        "explicit": item.get("trackExplicitness") == "explicit",
        "duration_ms": item.get("trackTimeMillis"),
    })


@app.get("/api/track/<int:itunes_id>/preview")
def check_preview(itunes_id: int):
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
            results = r.json().get("results") or []
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    if not results:
        return jsonify({"error": "not found"}), 404
    preview_url = results[0].get("previewUrl")
    available = bool(preview_url)
    return jsonify({
        "itunes_id": itunes_id,
        "preview_url": preview_url,
        "is_available": available,
        "can_stream": available,
        "note": "30-second preview only. Full tracks are not available via free public APIs.",
    })


@app.get("/api/track/<int:itunes_id>/preview/stream")
def stream_preview(itunes_id: int):
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
            results = r.json().get("results") or []
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502
    if not results or not results[0].get("previewUrl"):
        return jsonify({"error": "No preview available"}), 404
    preview_url = results[0]["previewUrl"]

    def generate():
        with httpx.stream("GET", preview_url, timeout=30.0) as resp:
            for chunk in resp.iter_bytes(chunk_size=8192):
                yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mp4",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/news")
def get_news():
    limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    if not supabase:
        return jsonify({"count": 0, "articles": [], "warning": "Supabase not configured"})
    try:
        resp = supabase.table("music_news").select("*").order("published_at", desc=True).limit(limit).execute()
        return jsonify({"count": len(resp.data or []), "articles": resp.data or []})
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
            supabase.table("track_metadata").upsert({
                "itunes_id": itunes_id, "title": title, "artist": artist,
                "artwork_url": artwork, "release_date": release, "raw_json": item,
            }, on_conflict="itunes_id").execute()
            supabase.table("top_charts").upsert({
                "chart_date": today.isoformat(), "year": today.year,
                "source": "apple_music_rss", "rank": i, "itunes_id": itunes_id,
                "title": title, "artist": artist, "artwork_url": artwork,
            }, on_conflict="chart_date,source,rank").execute()
            upserted += 1
        except Exception as exc:
            logger.warning("ingest row failed: %s", exc)
    return jsonify({"ingested": upserted, "chart_date": today.isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
