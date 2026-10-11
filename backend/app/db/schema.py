"""Tables and local migrations. Supabase migrations live in supabase/migrations.

Add a table in three places: a Table here, a SQLite migration below (never
edit an old one; append), and a numbered SQL file in supabase/migrations.
"""

from .repo import Table

# Tables reached through Repo (stores.repo). Memories use MemoryStore, which
# needs full-text search, but it is limited to one user the same way.
TABLES: dict[str, Table] = {
    # Supabase only (locally, settings are one JSON file per user).
    # One row per user (id = user_id): their settings as JSON (prefs.Prefs).
    "user_settings": Table("user_settings", frozenset({"data", "created_at", "updated_at"}), frozenset({"data"})),
    # Every change TalkBack made or was asked to make, with how to undo it (plan P4).
    "actions": Table(
        "actions",
        frozenset({
            "session_id", "call_id", "tool", "status", "summary", "target_kind", "target_id", "undo",
            "idempotency_key", "created_at", "updated_at", "finished_at", "undone_at",
        }),
        frozenset({"undo"}),
    ),
}

# Run in order, once each (PRAGMA user_version). Append only.
SQLITE_MIGRATIONS: list[str] = [
    # 1: memories with a full-text index kept in step by triggers.
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source = 'user_utterance'),
        utterance TEXT NOT NULL, created_at TEXT NOT NULL,
        confidence REAL NOT NULL
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(text, content='memories');
    CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
    END;
    CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
    END;
    CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, text)
            VALUES ('delete', old.rowid, old.text);
        INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
    END;
    """,
    # 2: accounts. Existing memories belong to the local user.
    """
    ALTER TABLE memories ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local';
    CREATE INDEX IF NOT EXISTS memories_user ON memories (user_id, created_at);
    """,
    # 3: correction-aware memory and the action history (plan P4). SQLite
    # cannot change a CHECK, so memories is rebuilt and its index refilled.
    """
    CREATE TABLE memories_v3 (
        id TEXT PRIMARY KEY, text TEXT NOT NULL, kind TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('user_utterance', 'user_text', 'user_edit', 'assistant_suggestion')),
        utterance TEXT NOT NULL, created_at TEXT NOT NULL, confidence REAL NOT NULL,
        user_id TEXT NOT NULL DEFAULT 'local',
        status TEXT NOT NULL DEFAULT 'confirmed'
            CHECK(status IN ('confirmed', 'suggested', 'superseded', 'dismissed')),
        slot TEXT, updated_at TEXT, superseded_by TEXT
    );
    INSERT INTO memories_v3 (id, text, kind, source, utterance, created_at, confidence, user_id)
        SELECT id, text, kind, source, utterance, created_at, confidence, user_id FROM memories;
    DROP TABLE memories;
    ALTER TABLE memories_v3 RENAME TO memories;
    CREATE INDEX memories_user ON memories (user_id, created_at);
    CREATE INDEX memories_slot ON memories (user_id, slot);
    DROP TABLE IF EXISTS memories_fts;
    CREATE VIRTUAL TABLE memories_fts USING fts5(text, content='memories');
    CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
    END;
    CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    END;
    CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
        INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
    END;
    INSERT INTO memories_fts(memories_fts) VALUES ('rebuild');

    CREATE TABLE actions (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT, call_id TEXT,
        tool TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL,
        target_kind TEXT, target_id TEXT, undo TEXT, idempotency_key TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT, undone_at TEXT,
        UNIQUE (user_id, idempotency_key)
    );
    CREATE INDEX actions_user ON actions (user_id, created_at);
    """,
]
