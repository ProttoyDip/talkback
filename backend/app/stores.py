"""Where data lives: Supabase when it is configured, else local files.

stores_for(settings, user_id) is how request handlers and the voice engine
reach a user's data; every repo it hands out is limited to that user.
"""

from dataclasses import dataclass

from .config import Settings
from .db.postgrest_repo import PostgrestRepo, shared_rest
from .db.repo import Repo
from .db.schema import SQLITE_MIGRATIONS, TABLES
from .db.sqlite_repo import SqliteDatabase, SqliteRepo
from .memory import MemoryStore
from .prefs import PrefsStore

# Until accounts exist (plan P2) everyone is this one local user.
LOCAL_USER = "local"


def uses_supabase(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_secret_key.get_secret_value())


def memory_store(settings: Settings):
    if uses_supabase(settings):
        from .supabase_store import SupabaseMemoryStore

        return SupabaseMemoryStore(settings.supabase_url, settings.supabase_secret_key)
    return MemoryStore(settings.memory_db_path)


def prefs_store(settings: Settings) -> PrefsStore:
    if uses_supabase(settings):
        from .supabase_store import SupabasePrefsStore

        return SupabasePrefsStore(settings.supabase_url, settings.supabase_secret_key)
    return PrefsStore(settings.settings_path)


def _repo(settings: Settings, table: str, user_id: str | None) -> Repo:
    spec = TABLES[table]
    if uses_supabase(settings):
        rest = shared_rest(settings.supabase_url, settings.supabase_secret_key.get_secret_value())
        return PostgrestRepo(rest, spec, user_id)
    return SqliteRepo(SqliteDatabase(settings.memory_db_path, SQLITE_MIGRATIONS), spec, user_id)


def repo(settings: Settings, table: str, user_id: str) -> Repo:
    """One user's rows of a table: every query is filtered by user_id."""
    if not user_id:
        raise ValueError("a user is required")
    return _repo(settings, table, user_id)


def system_repo(settings: Settings, table: str) -> Repo:
    """Rows of every user. Only for server jobs (the reminder scheduler); never a request handler."""
    return _repo(settings, table, None)


@dataclass(frozen=True)
class UserStores:
    settings: Settings
    user_id: str
    memory: MemoryStore
    prefs: PrefsStore

    def repo(self, table: str) -> Repo:
        return repo(self.settings, table, self.user_id)


def stores_for(settings: Settings, user_id: str = LOCAL_USER) -> UserStores:
    return UserStores(settings, user_id, memory_store(settings), prefs_store(settings))
