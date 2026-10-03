#!/usr/bin/env python3
"""
Music News Ecosystem — FastAPI Backend
======================================
Endpoints:
  GET  /health
  GET  /api/charts                     Live Apple Music RSS (proxied, no CORS issues)
  GET  /api/track/{itunes_id}          iTunes lookup + hi-res artwork
  GET  /api/track/{itunes_id}/preview  Check if 30s preview is downloadable
  POST /api/track/{itunes_id}/preview/check   Same, force probe + log to DB
  GET  /api/news                       Latest music_news from Supabase
  GET  /api/releases                   Release radar
  GET  /api/artists                    Top artists
  POST /api/ingest/charts              Pull RSS → upsert into top_charts + track_metadata
  GET  /api/db/tables                  List configured tables + row counts (admin)

Important:
  • iTunes / Apple Music only provide 30-second previews.
  • Full-track download is NOT supported by any free public API used here.
  • /preview endpoints tell you whether the 30s AAC is reachable (downloadable).

Env:
  SUPABASE_URL, SUPABASE_KEY
  (optional) ALLOWED_ORIGINS=https://your-miniapp.example.com
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("music-backend")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_RSS = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/{limit}/songs.json"

app = FastAPI(
    title="Music News Ecosystem API",
    version="1.0.0",
    description="Charts, metadata, preview availability, news — free public sources only.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase client ready")
else:
    logger.warning("SUPABASE_URL / SUPABASE_KEY missing — DB routes will degrade")


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────
class PreviewStatus(BaseModel):
    itunes_id: int
    preview_url: Optional[str] = None
    is_available: bool
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    can_stream: bool = Field(
        description="True if the 30-second AAC preview can be fetched"
    )
    note: str = Field(
        default="iTunes only provides 30-second previews. Full tracks are not available via free public APIs."
    )


class TrackCard(BaseModel):
    itunes_id: int
    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    artwork_url: Optional[str] = None
    preview_url: Optional[str] = None
    track_view_url: Optional[str] = None
    explicit: bool = False
    duration_ms: Optional[int] = None


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def hi_res(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return (
        url.replace("100x100bb", "600x600bb")
        .replace("100x100", "600x600")
        .replace("60x60bb", "600x600bb")
    )


async def itunes_lookup(itunes_id: int) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
        r.raise_for_status()
        results = r.json().get("results") or []
        return results[0] if results else None


def item_to_card(item: dict[str, Any]) -> TrackCard:
    return TrackCard(
        itunes_id=item.get("trackId") or item.get("collectionId") or 0,
        title=item.get("trackName") or item.get("collectionName") or "Unknown",
        artist=item.get("artistName") or "Unknown",
        album=item.get("collectionName"),
        genre=item.get("primaryGenreName"),
        year=(item.get("releaseDate") or "")[:4] or None,
        artwork_url=hi_res(item.get("artworkUrl100") or item.get("artworkUrl60")),
        preview_url=item.get("previewUrl"),
        track_view_url=item.get("trackViewUrl"),
        explicit=item.get("trackExplicitness") == "explicit",
        duration_ms=item.get("trackTimeMillis"),
    )


async def probe_preview(url: str) -> dict[str, Any]:
    """HEAD (fallback GET) a preview URL to see if it is reachable."""
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

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            # Prefer HEAD to avoid downloading the whole AAC
            r = await client.head(url)
            if r.status_code >= 400 or not r.headers.get("content-type"):
                r = await client.get(url, headers={"Range": "bytes=0-1023"})
            result["http_status"] = r.status_code
            result["content_type"] = r.headers.get("content-type")
            cl = r.headers.get("content-length")
            result["content_length"] = int(cl) if cl and cl.isdigit() else None
            ok = 200 <= r.status_code < 400
            # Accept audio/* or application/octet-stream
            ct = (result["content_type"] or "").lower()
            is_audio = "audio" in ct or "mpeg" in ct or "aac" in ct or "octet" in ct
            result["is_available"] = ok and (is_audio or result["content_length"] is not None)
            result["can_stream"] = result["is_available"]
        except Exception as exc:
            logger.warning("Preview probe failed for %s: %s", url, exc)
            result["http_status"] = 0
    return result


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    db_ok = False
    if supabase:
        try:
            supabase.table("backup_logs").select("id").limit(1).execute()
            db_ok = True
        except Exception:
            db_ok = False
    return {
        "status": "ok",
        "supabase": db_ok,
        "time": datetime.utcnow().isoformat() + "Z",
        "note": "Full music download is NOT supported. Only 30s iTunes previews.",
    }


@app.get("/api/charts")
async def get_charts(limit: int = Query(25, ge=1, le=100)):
    """Proxy Apple Music most-played RSS (avoids browser CORS)."""
    url = APPLE_RSS.format(limit=limit)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            raise HTTPException(502, f"Apple RSS unreachable: {exc}") from exc

    results = data.get("feed", {}).get("results") or []
    tracks = []
    for i, item in enumerate(results, 1):
        tracks.append(
            {
                "rank": i,
                "itunes_id": int(item["id"]) if str(item.get("id", "")).isdigit() else item.get("id"),
                "title": item.get("name"),
                "artist": item.get("artistName"),
                "year": (item.get("releaseDate") or "")[:4],
                "artwork_url": hi_res(item.get("artworkUrl100")),
                "genres": item.get("genres"),
                "url": item.get("url"),
            }
        )
    return {"source": "apple_music_rss", "count": len(tracks), "tracks": tracks}


@app.get("/api/track/{itunes_id}", response_model=TrackCard)
async def get_track(itunes_id: int):
    item = await itunes_lookup(itunes_id)
    if not item:
        raise HTTPException(404, f"Track {itunes_id} not found on iTunes")
    return item_to_card(item)


@app.get("/api/track/{itunes_id}/preview", response_model=PreviewStatus)
async def check_preview(itunes_id: int, persist: bool = False):
    """
    Check whether the 30-second preview is downloadable/streamable.
    Does NOT download a full track — that is impossible via free iTunes APIs.
    """
    item = await itunes_lookup(itunes_id)
    if not item:
        raise HTTPException(404, f"Track {itunes_id} not found")

    preview_url = item.get("previewUrl")
    probe = await probe_preview(preview_url or "")

    if persist and supabase and preview_url:
        try:
            supabase.table("preview_checks").insert(
                {
                    "itunes_id": itunes_id,
                    "preview_url": preview_url,
                    "is_available": probe["is_available"],
                    "http_status": probe["http_status"],
                    "content_type": probe["content_type"],
                    "content_length": probe["content_length"],
                }
            ).execute()
        except Exception as exc:
            logger.warning("Could not persist preview_check: %s", exc)

    return PreviewStatus(
        itunes_id=itunes_id,
        preview_url=preview_url,
        is_available=probe["is_available"],
        http_status=probe["http_status"],
        content_type=probe["content_type"],
        content_length=probe["content_length"],
        can_stream=probe["can_stream"],
    )


@app.post("/api/track/{itunes_id}/preview/check", response_model=PreviewStatus)
async def force_preview_check(itunes_id: int):
    """Same as GET …/preview?persist=true"""
    return await check_preview(itunes_id, persist=True)


@app.get("/api/track/{itunes_id}/preview/stream")
async def stream_preview(itunes_id: int):
    """
    Proxy the 30-second AAC so the Mini App can play it without CORS issues.
    Still only 30 seconds — not a full download.
    """
    item = await itunes_lookup(itunes_id)
    if not item or not item.get("previewUrl"):
        raise HTTPException(404, "No preview available for this track")

    url = item["previewUrl"]

    async def generate():
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise HTTPException(resp.status_code, "Upstream preview error")
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    yield chunk

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'inline; filename="preview_{itunes_id}.m4a"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.get("/api/news")
async def get_news(limit: int = Query(20, ge=1, le=100)):
    if not supabase:
        return {"count": 0, "articles": [], "warning": "Supabase not configured"}
    try:
        resp = (
            supabase.table("music_news")
            .select("*")
            .order("published_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"count": len(resp.data or []), "articles": resp.data or []}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/releases")
async def get_releases(limit: int = Query(20, ge=1, le=100)):
    if not supabase:
        return {"count": 0, "releases": [], "warning": "Supabase not configured"}
    try:
        resp = (
            supabase.table("release_radar")
            .select("*")
            .order("release_date", desc=False)
            .limit(limit)
            .execute()
        )
        return {"count": len(resp.data or []), "releases": resp.data or []}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/artists")
async def get_artists(limit: int = Query(20, ge=1, le=100)):
    if not supabase:
        return {"count": 0, "artists": [], "warning": "Supabase not configured"}
    try:
        resp = (
            supabase.table("top_artists")
            .select("*")
            .order("rank")
            .limit(limit)
            .execute()
        )
        return {"count": len(resp.data or []), "artists": resp.data or []}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/ingest/charts")
async def ingest_charts(limit: int = Query(50, ge=1, le=100)):
    """
    Pull current Apple Music most-played chart and upsert into
    track_metadata + top_charts. Safe to call on a schedule.
    """
    if not supabase:
        raise HTTPException(503, "Supabase not configured")

    url = APPLE_RSS.format(limit=limit)
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        results = r.json().get("feed", {}).get("results") or []

    today = date.today()
    year = today.year
    upserted = 0

    for i, item in enumerate(results, 1):
        itunes_id = int(item["id"]) if str(item.get("id", "")).isdigit() else None
        if not itunes_id:
            continue

        artwork = hi_res(item.get("artworkUrl100"))
        title = item.get("name") or "Unknown"
        artist = item.get("artistName") or "Unknown"
        release = (item.get("releaseDate") or "")[:10] or None

        # track_metadata
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

        # top_charts snapshot
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

    return {"ingested": upserted, "chart_date": today.isoformat(), "source": "apple_music_rss"}


@app.get("/api/db/tables")
async def db_tables():
    """Quick health of core tables (row counts)."""
    if not supabase:
        raise HTTPException(503, "Supabase not configured")

    tables = [
        "track_metadata",
        "top_charts",
        "music_news",
        "release_radar",
        "top_artists",
        "backup_logs",
        "preview_checks",
    ]
    out = {}
    for t in tables:
        try:
            # count via select with head — supabase-py returns count in some versions
            resp = supabase.table(t).select("id", count="exact").limit(1).execute()
            out[t] = {"ok": True, "count": getattr(resp, "count", len(resp.data or []))}
        except Exception as exc:
            out[t] = {"ok": False, "error": str(exc)[:200]}
    return out


@app.get("/")
async def root():
    return {
        "service": "Music News Ecosystem API",
        "docs": "/docs",
        "health": "/health",
        "important": (
            "This backend can verify and stream 30-second iTunes previews only. "
            "Full-song download is not possible with free public APIs."
        ),
    }


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend:app", host="0.0.0.0", port=port, reload=False)
