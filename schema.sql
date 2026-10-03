-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Track Metadata Catalogue
CREATE TABLE IF NOT EXISTS track_metadata (
    id              BIGSERIAL PRIMARY KEY,
    itunes_id       BIGINT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    album           TEXT,
    genre           TEXT,
    release_date    DATE,
    year            INT GENERATED ALWAYS AS (EXTRACT(YEAR FROM release_date)::INT) STORED,
    artwork_url     TEXT,
    preview_url     TEXT,
    track_view_url  TEXT,
    explicit        BOOLEAN DEFAULT FALSE,
    duration_ms     INT,
    stream_count    BIGINT,
    raw_json        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Top Charts Snapshots
CREATE TABLE IF NOT EXISTS top_charts (
    id              BIGSERIAL PRIMARY KEY,
    chart_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    year            INT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'apple_music_rss',
    rank            INT NOT NULL CHECK (rank > 0),
    itunes_id       BIGINT REFERENCES track_metadata(itunes_id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    streams         TEXT,
    artwork_url     TEXT,
    preview_url     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chart_date, source, rank)
);

-- 3. Music News Feed
CREATE TABLE IF NOT EXISTS music_news (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'THR',
    source_url      TEXT,
    image_url       TEXT,
    category        TEXT DEFAULT 'General',
    published_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Release Radar
CREATE TABLE IF NOT EXISTS release_radar (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    release_date    DATE NOT NULL,
    release_type    TEXT DEFAULT 'Album',
    artwork_url     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Top Artists by Genre / All-Time
CREATE TABLE IF NOT EXISTS top_artists (
    id              BIGSERIAL PRIMARY KEY,
    rank            INT NOT NULL,
    name            TEXT NOT NULL,
    genre           TEXT NOT NULL,
    total_streams   TEXT NOT NULL,
    artwork_url     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Backup Audit Logs
CREATE TABLE IF NOT EXISTS backup_logs (
    id              BIGSERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    row_count       INT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexing for performance
CREATE INDEX IF NOT EXISTS idx_track_itunes_id ON track_metadata (itunes_id);
CREATE INDEX IF NOT EXISTS idx_charts_date ON top_charts (chart_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_published ON music_news (published_at DESC);