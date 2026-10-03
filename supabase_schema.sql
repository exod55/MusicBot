-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS music_news (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    summary TEXT,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS top_charts (
    id BIGSERIAL PRIMARY KEY,
    rank INTEGER NOT NULL,
    track_title TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    year INTEGER,
    streams_formatted TEXT,
    itunes_id TEXT,
    artwork_url TEXT,
    preview_url TEXT,
    chart_category TEXT DEFAULT 'apple_top_100',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backup_logs (
    id BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    records_count INTEGER NOT NULL,
    status TEXT DEFAULT 'SUCCESS',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
