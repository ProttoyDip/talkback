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
]
