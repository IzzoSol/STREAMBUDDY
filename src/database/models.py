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

CREATE TABLE IF NOT EXISTS analytics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour TEXT NOT NULL,
    game TEXT DEFAULT '',
    platform TEXT DEFAULT 'api',
    query_count INTEGER DEFAULT 0,
    avg_response_ms REAL DEFAULT 0.0,
    error_count INTEGER DEFAULT 0,
    unique_sessions INTEGER DEFAULT 0,
    UNIQUE(hour, game, platform)
);

CREATE TABLE IF NOT EXISTS analytics_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    game TEXT DEFAULT '',
    platform TEXT DEFAULT 'api',
    query_count INTEGER DEFAULT 0,
    avg_response_ms REAL DEFAULT 0.0,
    error_count INTEGER DEFAULT 0,
    unique_sessions INTEGER DEFAULT 0,
    top_queries TEXT DEFAULT '[]',
    UNIQUE(date, game, platform)
);

CREATE TABLE IF NOT EXISTS platform_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT UNIQUE NOT NULL,
    is_active INTEGER DEFAULT 0,
    started_at TEXT,
    stopped_at TEXT,
    error_message TEXT DEFAULT '',
    config TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT DEFAULT 'info',
    source TEXT DEFAULT 'system',
    message TEXT NOT NULL,
    details TEXT DEFAULT '{}',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_queries_session ON queries(session_id);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_game_context_session ON game_context(session_id);
CREATE INDEX IF NOT EXISTS idx_analytics_hour ON analytics_hourly(hour);
CREATE INDEX IF NOT EXISTS idx_analytics_date ON analytics_daily(date);
CREATE TABLE IF NOT EXISTS strategy_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss TEXT NOT NULL,
    game TEXT DEFAULT '',
    swarm_result TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    UNIQUE(boss, game)
);

CREATE TABLE IF NOT EXISTS strategy_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER,
    agent_name TEXT NOT NULL,
    vote TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES strategy_cache(id)
);

CREATE TABLE IF NOT EXISTS notifications_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    title TEXT DEFAULT '',
    message TEXT DEFAULT '',
    success INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS language_prefs (
    session_id TEXT PRIMARY KEY,
    language TEXT DEFAULT 'en',
    auto_detect INTEGER DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    provider TEXT DEFAULT 'generic',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts(is_read);
CREATE INDEX IF NOT EXISTS idx_strategy_boss ON strategy_cache(boss, game);
CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications_log(channel);
