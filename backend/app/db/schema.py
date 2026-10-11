"""Tables and local migrations. Supabase migrations live in supabase/migrations.

Add a table in three places: a Table here, a SQLite migration below (never
edit an old one; append), and a numbered SQL file in supabase/migrations.
"""

from .repo import Table

# Tables reached through Repo (stores.repo). Memories still use MemoryStore,
# which needs full-text search; it moves here when it gains a user (plan P2).
TABLES: dict[str, Table] = {}

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
]
