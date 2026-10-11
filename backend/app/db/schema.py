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
    # Plan P5. Times are UTC ISO 8601 strings ("2026-10-12T09:00:00+00:00"),
    # so they sort and compare the same in SQLite and Postgres. Rows are
    # soft-deleted (deleted_at), which makes undo simple.
    "tasks": Table("tasks", frozenset({
        "title", "notes", "status", "due_at", "priority", "completed_at", "deleted_at", "created_at", "updated_at",
    })),
    "events": Table("events", frozenset({
        "title", "starts_at", "ends_at", "kind", "status", "task_id", "deleted_at", "created_at", "updated_at",
    })),
    "reminders": Table("reminders", frozenset({
        "text", "due_at", "status", "delivered_at", "delivered_via", "ack_at", "snooze_count", "deleted_at",
        "created_at", "updated_at",
    })),
    # Day plans waiting for the user's OK (plan P6).
    "proposals": Table(
        "proposals",
        frozenset({"date", "status", "items", "chosen", "message_id", "expires_at", "created_at", "updated_at"}),
        frozenset({"items", "chosen"}),
    ),
    # What to pick up in a later conversation (plan P7).
    "conversation_states": Table(
        "conversation_states",
        frozenset({
            "session_id", "goal", "decisions", "pending", "tools_used", "recent_turns", "status", "closed_at",
            "created_at", "updated_at",
        }),
        frozenset({"decisions", "pending", "tools_used", "recent_turns"}),
    ),
    "user_skills": Table(
        "user_skills",
        frozenset({"name", "triggers", "allowed_tools", "instructions", "summary", "enabled", "created_at", "updated_at"}),
        frozenset({"triggers", "allowed_tools"}),
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
    # 4: tasks, calendar, reminders and your own skills (plan P5).
    """
    CREATE TABLE tasks (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, notes TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'done', 'cancelled')),
        due_at TEXT, priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('low', 'normal', 'high')),
        completed_at TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX tasks_user ON tasks (user_id, status, due_at);
    CREATE TABLE events (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL,
        starts_at TEXT NOT NULL, ends_at TEXT NOT NULL CHECK(ends_at > starts_at),
        kind TEXT NOT NULL DEFAULT 'block' CHECK(kind IN ('block', 'meeting', 'focus', 'personal')),
        status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'cancelled')),
        task_id TEXT, deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX events_user ON events (user_id, starts_at);
    CREATE TABLE reminders (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, text TEXT NOT NULL, due_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled'
            CHECK(status IN ('scheduled', 'delivered', 'acknowledged', 'cancelled', 'missed')),
        delivered_at TEXT, delivered_via TEXT, ack_at TEXT, snooze_count INTEGER NOT NULL DEFAULT 0,
        deleted_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX reminders_due ON reminders (status, due_at);
    CREATE TABLE user_skills (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, triggers TEXT NOT NULL,
        allowed_tools TEXT NOT NULL, instructions TEXT NOT NULL, summary TEXT,
        enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX user_skills_user ON user_skills (user_id);
    """,
    # 5: day plans waiting for the user's OK (plan P6).
    """
    CREATE TABLE proposals (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'accepted', 'partially_applied', 'rejected', 'superseded', 'expired')),
        items TEXT NOT NULL, chosen TEXT, message_id TEXT, expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX proposals_user ON proposals (user_id, date, status);
    """,
    # 6: resume an unfinished conversation (plan P7).
    """
    CREATE TABLE conversation_states (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL, goal TEXT NOT NULL,
        decisions TEXT, pending TEXT, tools_used TEXT, recent_turns TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resumed', 'dismissed')),
        closed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE INDEX conversation_states_user ON conversation_states (user_id, status, updated_at);
    """,
]
