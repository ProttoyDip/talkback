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
        from .tool_bridge import ToolBridge
        from .tools.weather import weather_tool
        from .tools.web_search import web_search_tool

        http = httpx.AsyncClient(follow_redirects=False)
        # Weather needs no key (Open-Meteo). Web search only with a Tavily key.
        tools = [weather_tool(http)]
        if settings.tavily_api_key.get_secret_value():
            tools.append(web_search_tool(http, settings.tavily_api_key))
        engine = CascadeEngine(
            stt=RivaStreamingASR(
                settings.riva_server, settings.asr_function_id, settings.nvidia_api_key, settings.asr_stop_history_ms
            ),
            tts=RivaTTS(settings.riva_server, settings.tts_function_id, settings.nvidia_api_key, settings.tts_voice),
            llm=LlmClient(providers_from_settings(settings), http),
            bridge_factory=lambda session_id, emit, say_filler: ToolBridge(session_id, tools, emit, say_filler),
        )
        return EngineChoice(engine, http=http)
    return EngineChoice(None, f"The voice engine '{kind}' is not available in this build.")


def get_engine_factory() -> EngineFactory:
    """FastAPI dependency, so tests can swap in fake engines."""
    return create_engine
