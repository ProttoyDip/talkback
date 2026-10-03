"""Settings and skills REST routes (architecture.md 3.2). All need the session token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from .config import Settings, get_settings
from .llm import providers_from_settings
from .memory_routes import bearer
from .prefs import Prefs, PrefsStore
from .protocol import (
    Id,
    ModelOption,
    ModelsView,
    ProviderInfo,
    SettingsUpdate,
    SettingsView,
    SkillList,
    SkillRunAccepted,
    ToolSetting,
)
from .session import registry
from .skills import load_skills
from .tokens import SessionClaims, verify_token

TOOL_DESCRIPTIONS = {
    "weather": "Looks up the forecast for a place you name. It sends only that place name.",
    "web_search": "Searches the web with your question. It sends only that text to the search provider.",
    "memory_read": "Reads the memories you asked TalkBack to keep.",
    "memory_delete": "Deletes memories, only after you say yes.",
}
VOICE_MODEL = "NVIDIA Parakeet and Magpie TTS (VoiceChat when available)"


def claims(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> SessionClaims:
    found = verify_token(settings.signing_key(), credentials.credentials) if credentials else None
    if found is None:
        raise HTTPException(401, "Invalid or expired session token", headers={"WWW-Authenticate": "Bearer"})
    return found


settings_router = APIRouter(prefix="/api/settings", dependencies=[Depends(claims)])
skills_router = APIRouter(prefix="/api/skills", dependencies=[Depends(claims)])


def build_view(settings: Settings, prefs: Prefs) -> SettingsView:
    configured = {p.id for p in providers_from_settings(settings)}
    options = []
    for provider_id, model in (("nebius", settings.nebius_llm_model), ("openrouter", settings.openrouter_llm_model)):
        enabled = provider_id == "nebius" or prefs.provider_enabled(provider_id)
        options.append(
            ModelOption(
                id=f"{provider_id}:{model}",
                provider=provider_id,
                model=model,
                nvidia=model.startswith("nvidia/"),
                available=provider_id in configured and enabled,
            )
        )
    options.sort(key=lambda o: (not o.nvidia, not o.available))
    default = next((o.id for o in options if o.available), options[0].id)
    chosen_ok = any(o.id == prefs.planner_model and o.available for o in options)
    selected = prefs.planner_model if chosen_ok else default

    def provider(id_, name, role, primary, key) -> ProviderInfo:
        return ProviderInfo(
            id=id_,
            name=name,
            role=role,
            primary=primary,
            enabled=True if primary else prefs.provider_enabled(id_),
            configured=bool(key.get_secret_value()),
            receives_user_words=True,
        )

    providers = [
        provider("nebius", "Nebius Token Factory", "planner", True, settings.nebius_api_key),
        provider("openrouter", "OpenRouter", "planner", False, settings.openrouter_api_key),
        provider("tavily", "Tavily", "search", True, settings.tavily_api_key),
        provider("perplexity", "Perplexity", "search", False, settings.perplexity_api_key),
    ]
    tools = {
        name: ToolSetting(enabled=prefs.tool_enabled(name), description=text)
        for name, text in TOOL_DESCRIPTIONS.items()
    }
    return SettingsView(
        tools=tools,
        save_recordings=prefs.save_recordings,
        transcripts_in_logs=prefs.transcripts_in_logs,
        interrupt_sensitivity=prefs.interrupt_sensitivity,
        answer_length=prefs.answer_length,
        models=ModelsView(
            voice_model=VOICE_MODEL, planner_model=selected, planner_options=options, providers=providers
        ),
    )


def get_prefs(settings: Annotated[Settings, Depends(get_settings)]) -> PrefsStore:
    return PrefsStore(settings.settings_path)


@settings_router.get("", response_model=SettingsView)
def read_settings(
    settings: Annotated[Settings, Depends(get_settings)], store: Annotated[PrefsStore, Depends(get_prefs)]
) -> SettingsView:
    return build_view(settings, store.load())


@settings_router.patch("", response_model=SettingsView)
def update_settings(
    update: SettingsUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[PrefsStore, Depends(get_prefs)],
) -> SettingsView:
    prefs = store.load()
    for name, enabled in (update.tools or {}).items():
        prefs.tools[name] = enabled
    if update.save_recordings is not None:
        prefs.save_recordings = update.save_recordings
    if update.transcripts_in_logs is not None:
        prefs.transcripts_in_logs = update.transcripts_in_logs
    if update.interrupt_sensitivity is not None:
        prefs.interrupt_sensitivity = update.interrupt_sensitivity
    if update.answer_length is not None:
        prefs.answer_length = update.answer_length
    for name, enabled in (update.providers or {}).items():
        prefs.providers[name] = enabled
    if update.planner_model is not None:
        options = {o.id: o for o in build_view(settings, prefs).models.planner_options}
        option = options.get(update.planner_model)
        if option is None or not option.available:
            raise HTTPException(422, "That planner model is not available")
        prefs.planner_model = update.planner_model
    store.save(prefs)
    return build_view(settings, prefs)


def get_skills(settings: Annotated[Settings, Depends(get_settings)]):
    return load_skills(settings.skills_dir)


@skills_router.get("", response_model=SkillList)
def list_skills(skills: Annotated[list, Depends(get_skills)]) -> SkillList:
    return SkillList(items=[s.item() for s in skills])


@skills_router.post("/{skill_id}/run", response_model=SkillRunAccepted, status_code=202)
def run_skill(
    skill_id: Id, found: Annotated[SessionClaims, Depends(claims)], skills: Annotated[list, Depends(get_skills)]
) -> SkillRunAccepted:
    if skill_id not in {s.id for s in skills}:
        raise HTTPException(404, "Skill not found")
    session = registry.live.get(found.session_id)
    engine = session.engine if session else None
    if engine is None or not hasattr(engine, "run_skill"):
        raise HTTPException(409, "Start a conversation first")
    if not engine.run_skill(skill_id):
        raise HTTPException(404, "Skill not found")
    return SkillRunAccepted(run_id=uuid.uuid4().hex[:16])
