CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    game TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    query_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    query TEXT NOT NULL,
    game TEXT DEFAULT '',
    topic TEXT DEFAULT '',
    answer TEXT DEFAULT '',
    confidence REAL DEFAULT 0.0,
    sources TEXT DEFAULT '[]',
    processing_time_ms REAL DEFAULT 0.0,
    vision_data TEXT DEFAULT '{}',
    web_results TEXT DEFAULT '[]',
    reddit_results TEXT DEFAULT '[]',
    wiki_results TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS cache (
    cache_key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT UNIQUE NOT NULL,
    label TEXT DEFAULT '',
    tier TEXT DEFAULT 'free',
    is_active INTEGER DEFAULT 1,
    rate_limit_per_min INTEGER DEFAULT 30,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS game_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_name TEXT NOT NULL,
    scene TEXT DEFAULT '',
    objectives TEXT DEFAULT '[]',
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_queries_session ON queries(session_id);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_game_context_session ON game_context(session_id);
