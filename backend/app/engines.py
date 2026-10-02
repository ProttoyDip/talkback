"""Builds the voice engine selected by VOICE_ENGINE (config.py)."""

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .config import Settings
from .voice_engine import VoiceEngine


@dataclass(frozen=True)
class EngineChoice:
    engine: VoiceEngine | None
    # Why there is no engine, in words for the user (None: on purpose).
    problem: str | None = None
    # Closed with the session.
    http: httpx.AsyncClient | None = None


EngineFactory = Callable[[Settings], EngineChoice]


def create_engine(settings: Settings) -> EngineChoice:
    kind = settings.voice_engine
    if kind == "none":
        return EngineChoice(None)
    if kind == "cascade":
        if not settings.nvidia_api_key.get_secret_value():
            return EngineChoice(None, "Speech isn't set up yet. Add NVIDIA_API_KEY to backend/.env and restart.")
        # Imported here so the gRPC client loads only when it is used.
        from .cascade_engine import CascadeEngine
        from .llm import LlmClient, providers_from_settings
        from .speech.nvidia import RivaStreamingASR, RivaTTS
        from .memory import MemoryStore
        from .prefs import PrefsStore
        from .skills import load_skills
        from .tool_bridge import ToolBridge
        from .tools.memory import memory_tools
        from .tools.weather import weather_tool
        from .tools.web_search import web_search_tool

        prefs = PrefsStore(settings.settings_path).load()
        http = httpx.AsyncClient(follow_redirects=False)
        memory = MemoryStore(settings.memory_db_path)
        # Weather needs no key (Open-Meteo). Web search needs a Tavily or Perplexity key.
        tools = [weather_tool(http), *memory_tools(memory)]
        if settings.tavily_api_key.get_secret_value() or settings.perplexity_api_key.get_secret_value():
            tools.append(web_search_tool(http, settings.tavily_api_key, settings.perplexity_api_key))
        # The user's tool switches (Settings) apply when a session starts.
        tools_on = {tool.name for tool in tools if prefs.tool_enabled(tool.name)}
        providers = [p for p in providers_from_settings(settings) if p.primary or prefs.provider_enabled(p.id)]
        chosen = [p for p in providers if f"{p.id}:{p.model}" == prefs.planner_model]
        providers = chosen + [p for p in providers if p not in chosen]
        engine = CascadeEngine(
            stt=RivaStreamingASR(
                settings.riva_server, settings.asr_function_id, settings.nvidia_api_key, settings.asr_stop_history_ms
            ),
            tts=RivaTTS(settings.riva_server, settings.tts_function_id, settings.nvidia_api_key, settings.tts_voice),
            llm=LlmClient(providers, http),
            bridge_factory=lambda session_id, emit, say_filler: _bridge(
                ToolBridge(session_id, tools, emit, say_filler), tools_on),
            memory_store=memory,
            skills=load_skills(settings.skills_dir),
        )
        return EngineChoice(engine, http=http)
    return EngineChoice(None, f"The voice engine '{kind}' is not available in this build.")


def _bridge(bridge, enabled: set[str]):
    bridge.set_enabled(enabled)
    return bridge


def get_engine_factory() -> EngineFactory:
    """FastAPI dependency, so tests can swap in fake engines."""
    return create_engine
