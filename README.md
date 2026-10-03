# Music News Ecosystem

Telegram Mini App + Bot + FastAPI backend + Supabase.

## What’s included

| File | Role |
|------|------|
| `index.html` | Single-file Telegram Mini App (charts, news, 3D, deep-links) |
| `bot.py` | Deep-link handler + daily in-memory CSV backups to private channel |
| `backend.py` | FastAPI: charts proxy, track lookup, **preview downloadability check**, DB ingest |
| `schema.sql` | Supabase / PostgreSQL tables |
| `requirements.txt` | Python deps |
| `.env.example` | Environment variables |

## Critical note on “download music”

**iTunes / Apple Music public APIs only expose 30-second AAC previews.**  
There is no free, legal full-track download endpoint used in this stack.

The backend lets you **check whether that 30s preview is reachable**:

```http
GET /api/track/{itunes_id}/preview
→ { "is_available": true, "can_stream": true, "content_type": "audio/mp4", ... }
```

You can also stream the preview through the backend (CORS-safe for the Mini App):

```http
GET /api/track/{itunes_id}/preview/stream
```

## Setup

### 1. Database
1. Create a Supabase project.
2. SQL Editor → paste and run `schema.sql`.

### 2. Backend (Render Web Service or local)
```bash
pip install -r requirements.txt
export SUPABASE_URL=... SUPABASE_KEY=...
uvicorn backend:app --host 0.0.0.0 --port 8000
```
Docs: `http://localhost:8000/docs`

### 3. Bot (Render Background Worker)
```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_BACKUP_CHANNEL_ID=-100...
export SUPABASE_URL=... SUPABASE_KEY=...
python bot.py
```

### 4. Mini App
- Host `index.html` (any static host or same Render service).
- In BotFather → Bot Settings → Menu Button / Web App → set URL.
- In `index.html` change `BOT_USERNAME` to your bot username.
- Optionally point chart fetch to your backend:  
  `https://your-api.onrender.com/api/charts` instead of the public RSS (avoids CORS).

## Useful API routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + Supabase ping |
| GET | `/api/charts?limit=25` | Apple most-played (proxied) |
| GET | `/api/track/{id}` | Full metadata + 600×600 art |
| GET | `/api/track/{id}/preview` | **Can the 30s preview be downloaded?** |
| GET | `/api/track/{id}/preview/stream` | Stream the 30s AAC |
| POST | `/api/ingest/charts` | Pull RSS → `track_metadata` + `top_charts` |
| GET | `/api/news` | Rows from `music_news` |
| GET | `/api/db/tables` | Row counts for all core tables |

## Deploy checklist
1. Run `schema.sql` in Supabase  
2. Deploy `backend.py` (Web Service)  
3. Deploy `bot.py` (Background Worker)  
4. Host `index.html` and wire BotFather Mini App URL  
5. Create private backup channel, add bot as admin, set `TELEGRAM_BACKUP_CHANNEL_ID`  
6. Call `POST /api/ingest/charts` once (or on a cron) to seed charts  
