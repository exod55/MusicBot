#!/usr/bin/env python3
"""
Music News Ecosystem — Backend API
"""

import os
from datetime import date
import httpx
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

app = Flask(__name__)
CORS(app)

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"
APPLE_RSS = "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json"


@app.get("/api/charts")
def get_charts():
    with httpx.Client(timeout=15.0) as client:
        r = client.get(APPLE_RSS)
        return jsonify(r.json().get("feed", {}).get("results", []))


@app.get("/api/track/<int:itunes_id>/preview/stream")
def stream_preview(itunes_id: int):
    with httpx.Client(timeout=10.0) as client:
        r = client.get(ITUNES_LOOKUP, params={"id": itunes_id, "entity": "song"})
        results = r.json().get("results") or []
        if not results or not results[0].get("previewUrl"):
            return jsonify({"error": "No preview available"}), 404
        preview_url = results[0]["previewUrl"]

    def generate():
        with httpx.stream("GET", preview_url) as resp:
            for chunk in resp.iter_bytes(chunk_size=8192):
                yield chunk

    return Response(stream_with_context(generate()), mimetype="audio/mp4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))