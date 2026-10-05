-- InvestLens database schema (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- One row per user: the last requirements they entered
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    budget  REAL    NOT NULL DEFAULT 100000,
    risk    INTEGER NOT NULL DEFAULT 2 CHECK (risk IN (1,2,3)),  -- 1 aggressive, 2 balanced, 3 conservative
    horizon TEXT    NOT NULL DEFAULT 'medium' CHECK (horizon IN ('short','medium','long'))
);

-- The balance-sheet rows from the "Companies" table (replaced on every analysis)
CREATE TABLE IF NOT EXISTS companies (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name     TEXT    NOT NULL,
    ca       REAL    NOT NULL DEFAULT 0,   -- current assets
    cl       REAL    NOT NULL DEFAULT 0,   -- current liabilities
    debt     REAL    NOT NULL DEFAULT 0,   -- total debt
    eq       REAL    NOT NULL DEFAULT 0,   -- equity
    cash     REAL    NOT NULL DEFAULT 0,
    rev      REAL    NOT NULL DEFAULT 0,   -- revenue
    ni       REAL    NOT NULL DEFAULT 0    -- net income
);
CREATE INDEX IF NOT EXISTS idx_companies_user ON companies(user_id, position);

-- History of Layer 1 runs (full result kept as JSON)
CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    budget      REAL    NOT NULL,
    risk        INTEGER NOT NULL,
    result_json TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id, id DESC);

-- History of Layer 2 buy signals
CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT    NOT NULL,
    prices_json  TEXT    NOT NULL,
    timing_score REAL    NOT NULL,
    final_score  INTEGER NOT NULL,
    signal       TEXT    NOT NULL CHECK (signal IN ('G','Y','R')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_user ON signals(user_id, company_name, id DESC);

-- AI assistant conversation log
CREATE TABLE IF NOT EXISTS chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT    NOT NULL,
    horizon      TEXT    NOT NULL,
    role         TEXT    NOT NULL CHECK (role IN ('user','bot')),
    content      TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, company_name, id);
