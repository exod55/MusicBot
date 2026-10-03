-- ============================================================
-- Music News Ecosystem — Supabase / PostgreSQL Schema
-- Run this in Supabase SQL Editor (or psql)
-- ============================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- fuzzy search on titles/artists

-- ------------------------------------------------------------
-- 1. track_metadata
--    Core catalogue of songs (from iTunes / Apple Music RSS)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS track_metadata (
    id              BIGSERIAL PRIMARY KEY,
    itunes_id       BIGINT UNIQUE NOT NULL,          -- Apple / iTunes track ID
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    album           TEXT,
    genre           TEXT,
    release_date    DATE,
    year            INT GENERATED ALWAYS AS (EXTRACT(YEAR FROM release_date)::INT) STORED,
    artwork_url     TEXT,                            -- preferably 600x600
    preview_url     TEXT,                            -- 30-second AAC preview
    track_view_url  TEXT,                            -- Apple Music deep link
    explicit        BOOLEAN DEFAULT FALSE,
    duration_ms     INT,
    stream_count    BIGINT,                          -- optional external metric
    rank_peak       INT,                             -- best chart position ever seen
    raw_json        JSONB,                           -- full iTunes payload (optional)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_track_itunes_id ON track_metadata (itunes_id);
CREATE INDEX IF NOT EXISTS idx_track_artist_trgm ON track_metadata USING gin (artist gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_track_title_trgm ON track_metadata USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_track_year ON track_metadata (year);

-- ------------------------------------------------------------
-- 2. top_charts
--    Snapshot of chart positions by date / year / source
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS top_charts (
    id              BIGSERIAL PRIMARY KEY,
    chart_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    year            INT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'apple_music_rss',  -- apple_music_rss | manual | etc.
    rank            INT NOT NULL CHECK (rank > 0),
    itunes_id       BIGINT REFERENCES track_metadata(itunes_id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    streams         TEXT,                            -- display string e.g. "2.48B"
    streams_raw     BIGINT,                          -- numeric if available
    artwork_url     TEXT,
    preview_url     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chart_date, source, rank)
);

CREATE INDEX IF NOT EXISTS idx_charts_date ON top_charts (chart_date DESC);
CREATE INDEX IF NOT EXISTS idx_charts_year ON top_charts (year);
CREATE INDEX IF NOT EXISTS idx_charts_itunes ON top_charts (itunes_id);

-- ------------------------------------------------------------
-- 3. music_news
--    Articles from THR, RSS-Bridge, newspaper scrapers, etc.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS music_news (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    summary         TEXT,
    content         TEXT,
    source          TEXT NOT NULL,                   -- "The Hollywood Reporter", etc.
    source_url      TEXT UNIQUE,                     -- canonical article URL
    category        TEXT,                            -- Industry | Legal | Touring | AI | …
    image_url       TEXT,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_featured     BOOLEAN DEFAULT FALSE,
    raw_json        JSONB
);

CREATE INDEX IF NOT EXISTS idx_news_published ON music_news (published_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_news_category ON music_news (category);
CREATE INDEX IF NOT EXISTS idx_news_source ON music_news (source);

-- ------------------------------------------------------------
-- 4. release_radar
--    Upcoming / recent releases (MusicBrainz + trackers)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS release_radar (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    release_date    DATE,
    release_type    TEXT,                            -- Album | EP | Single | Deluxe
    mbid            UUID,                            -- MusicBrainz ID if known
    itunes_id       BIGINT,
    artwork_url     TEXT,
    status          TEXT DEFAULT 'upcoming',         -- upcoming | released | delayed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_releases_date ON release_radar (release_date);
CREATE INDEX IF NOT EXISTS idx_releases_status ON release_radar (status);

-- ------------------------------------------------------------
-- 5. top_artists
--    Aggregated artist stats (optional cache)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS top_artists (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    genre           TEXT,
    total_streams   TEXT,                            -- display e.g. "98.4B"
    total_streams_raw BIGINT,
    rank            INT,
    image_url       TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 6. backup_logs
--    Written by the Telegram bot after each CSV backup
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backup_logs (
    id              BIGSERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    row_count       INT,
    status          TEXT NOT NULL DEFAULT 'success', -- success | failed
    error_message   TEXT,
    file_size_bytes BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backup_created ON backup_logs (created_at DESC);

-- ------------------------------------------------------------
-- 7. preview_checks  (optional audit of downloadability)
--    Backend writes here when it probes a preview URL
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS preview_checks (
    id              BIGSERIAL PRIMARY KEY,
    itunes_id       BIGINT NOT NULL,
    preview_url     TEXT,
    is_available    BOOLEAN,
    http_status     INT,
    content_type    TEXT,
    content_length  BIGINT,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preview_itunes ON preview_checks (itunes_id);
CREATE INDEX IF NOT EXISTS idx_preview_checked ON preview_checks (checked_at DESC);

-- ------------------------------------------------------------
-- Helper: auto-update updated_at
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_track_updated ON track_metadata;
CREATE TRIGGER trg_track_updated
    BEFORE UPDATE ON track_metadata
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_release_updated ON release_radar;
CREATE TRIGGER trg_release_updated
    BEFORE UPDATE ON release_radar
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- Row Level Security (optional – enable if using anon key from frontend)
-- For a pure backend + service_role setup you can leave RLS off.
-- ------------------------------------------------------------
-- ALTER TABLE track_metadata ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Public read tracks" ON track_metadata FOR SELECT USING (true);

COMMENT ON TABLE track_metadata IS 'Core song catalogue from iTunes / Apple Music';
COMMENT ON TABLE top_charts IS 'Daily / yearly chart snapshots';
COMMENT ON TABLE music_news IS 'Scraped / RSS music news articles';
COMMENT ON TABLE backup_logs IS 'Audit trail of Telegram CSV backups';
COMMENT ON TABLE preview_checks IS 'Results of preview URL reachability probes';
