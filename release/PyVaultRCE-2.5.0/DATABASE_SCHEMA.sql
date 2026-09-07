-- PyVault schema reference. The app creates/migrates sessions.db on startup.

CREATE TABLE comments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                username        TEXT NOT NULL,
                body            TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );

CREATE TABLE config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

CREATE TABLE profiles (
                username        TEXT PRIMARY KEY,
                verified        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE sessions (
                session_id   TEXT PRIMARY KEY,
                python_code  TEXT NOT NULL,
                execution_count INTEGER NOT NULL DEFAULT 0,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            , owner_token_hash TEXT DEFAULT NULL, expires_at TEXT DEFAULT NULL, max_executions TEXT DEFAULT 0, label TEXT DEFAULT '', libraries TEXT DEFAULT '', share_slug TEXT DEFAULT NULL, username TEXT DEFAULT 'anonymous', description TEXT DEFAULT '', tags TEXT DEFAULT '', views TEXT DEFAULT 0);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE view_events (
                session_id      TEXT NOT NULL,
                visitor_key     TEXT NOT NULL,
                viewed_on       TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                PRIMARY KEY (session_id, visitor_key, viewed_on),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
