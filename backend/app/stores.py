"""Where memories and settings live: Supabase when it is configured, else local files."""

from .config import Settings
from .memory import MemoryStore
from .prefs import PrefsStore


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
