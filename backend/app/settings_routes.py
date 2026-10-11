"""Settings and skills REST routes (architecture.md 3.2). All need the session token."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from .config import Settings, get_settings
from .timeutil import valid_zone
from .llm import providers_from_settings
from .auth import Claims, session_claims
from .prefs import Prefs, PrefsStore
from .stores import prefs_store
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
    SkillCreate,
    SkillItem,
    SkillUpdate,
)
from .session import registry
from . import resume
from .skills import MAX_USER_SKILLS, SkillProblem, check_user_skill, load_skills, user_skill
from .stores import repo

TOOL_DESCRIPTIONS = {
    "weather": "Looks up the forecast for a place you name. It sends only that place name.",
    "web_search": "Searches the web with your question. It sends only that text to the search provider.",
    "memory_read": "Reads the memories you asked TalkBack to keep.",
    "memory_delete": "Deletes memories, only after you say yes.",
    "memory_suggest": "Suggests a memory you can keep or dismiss. Not used until you keep it.",
    "task_add": "Adds and changes your tasks. Each change can be undone.",
    "calendar_add": "Adds and moves blocks in your calendar. Each change can be undone.",
    "reminder_set": "Sets reminders that notify you later, only after you say yes.",
}
# One switch covers a group: turning off task_add turns off every task tool.
TOOL_GROUPS = {
    "task_add": ("task_list", "task_add", "task_update", "task_delete"),
    "calendar_add": ("calendar_list", "calendar_add", "calendar_update", "calendar_delete", "day_plan_propose",
                     "day_plan_apply"),
    "reminder_set": ("reminder_set", "reminder_update"),
}
def voice_engine_view(settings: Settings) -> tuple[str, bool]:
    """What can actually serve voice now (engines.py), and whether it is full-duplex."""
    if settings.voice_engine == "cascade" and not settings.nvidia_api_key.get_secret_value():
        return "Speech is not set up on this server", False
    if settings.voice_engine not in BUILT_ENGINES:
        return "Speech is not available on this server", False
    return VOICE_ENGINES[settings.voice_engine]


# Engines this build can start (engines.create_engine); VoiceChat is planned.
BUILT_ENGINES = {"cascade", "fake", "none"}
# What serves voice for each VOICE_ENGINE, and whether it is full-duplex.
VOICE_ENGINES = {
    "cascade": ("NVIDIA Parakeet speech-to-text + Magpie TTS", False),
    "voicechat": ("NVIDIA VoiceChat", True),
    "fake": ("Scripted test voice", False),
    "none": ("No voice engine", False),
}


settings_router = APIRouter(prefix="/api/settings", dependencies=[Depends(session_claims)])
skills_router = APIRouter(prefix="/api/skills", dependencies=[Depends(session_claims)])


def build_view(settings: Settings, prefs: Prefs) -> SettingsView:
    configured = {p.id for p in providers_from_settings(settings)}
    options = []
    planner_models = (
        ("nebius", settings.nebius_llm_model),
        ("openrouter", settings.openrouter_llm_model),
        ("nararouter", settings.nararouter_llm_model),
        ("experimentallab", settings.experimentallab_llm_model),
    )
    for provider_id, model in planner_models:
        enabled = provider_id == "nebius" or prefs.provider_enabled(provider_id)
        options.append(
            ModelOption(
                id=f"{provider_id}:{model}",
                provider=provider_id,
                model=model,
                nvidia=model.startswith("nvidia/") or "nemotron" in model.lower(),
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
        provider("nararouter", "Nararouter", "planner", False, settings.nararouter_api_key),
        provider("experimentallab", "Experiential Labs", "planner", False, settings.experimentallab_api_key),
        provider("tavily", "Tavily", "search", True, settings.tavily_api_key),
        provider("perplexity", "Perplexity", "search", False, settings.perplexity_api_key),
    ]
    tools = {
        name: ToolSetting(enabled=prefs.tool_enabled(name), description=text)
        for name, text in TOOL_DESCRIPTIONS.items()
    }
    voice_model, full_duplex = voice_engine_view(settings)
    return SettingsView(
        tools=tools,
        save_recordings=prefs.save_recordings,
        transcripts_in_logs=prefs.transcripts_in_logs,
        interrupt_sensitivity=prefs.interrupt_sensitivity,
        answer_length=prefs.answer_length,
        timezone=prefs.timezone,
        resume_sessions=prefs.resume_sessions,
        keep_recent_turns=prefs.keep_recent_turns,
        models=ModelsView(
            voice_model=voice_model, full_duplex=full_duplex,
            planner_model=selected, planner_options=options, providers=providers,
        ),
    )


def get_prefs(settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> PrefsStore:
    return prefs_store(settings, claims.user_id)  # this user's settings


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
    claims: Claims,
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
    if update.resume_sessions is not None:
        prefs.resume_sessions = update.resume_sessions
        if not update.resume_sessions:  # off: nothing stays stored
            resume.forget(repo(settings, "conversation_states", claims.user_id))
    if update.keep_recent_turns is not None:
        prefs.keep_recent_turns = update.keep_recent_turns
        if not update.keep_recent_turns:
            resume.forget(repo(settings, "conversation_states", claims.user_id), turns_only=True)
    if update.timezone is not None:
        if not valid_zone(update.timezone):
            raise HTTPException(422, "Unknown time zone")
        prefs.timezone = update.timezone
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


def get_skills(settings: Annotated[Settings, Depends(get_settings)], claims: Claims):
    """Built-in skills, then this user's own."""
    rows = repo(settings, "user_skills", claims.user_id).select(order="created_at.asc", limit=MAX_USER_SKILLS)
    return load_skills(settings.skills_dir) + [user_skill(row) for row in rows]


@skills_router.get("", response_model=SkillList)
def list_skills(skills: Annotated[list, Depends(get_skills)]) -> SkillList:
    return SkillList(items=[s.item() for s in skills])


def _reload_live_skills(settings: Settings, user_id: str) -> None:
    """Open conversations of this user pick up the change at once."""
    skills = None
    for session in list(registry.live.values()):
        if session.user_id == user_id and hasattr(session.engine, "skills"):
            if skills is None:
                rows = repo(settings, "user_skills", user_id).select(order="created_at.asc", limit=MAX_USER_SKILLS)
                skills = load_skills(settings.skills_dir) + [s for s in map(user_skill, rows) if s.enabled]
            session.engine.skills = skills


@skills_router.post("", response_model=SkillItem, status_code=201)
def create_skill(
    body: SkillCreate, settings: Annotated[Settings, Depends(get_settings)], claims: Claims,
    skills: Annotated[list, Depends(get_skills)],
) -> SkillItem:
    if sum(not s.builtin for s in skills) >= MAX_USER_SKILLS:
        raise HTTPException(422, f"You can have up to {MAX_USER_SKILLS} skills.")
    try:
        triggers = check_user_skill(body.name, body.triggers, body.allowed_tools, skills)
    except SkillProblem as problem:
        raise HTTPException(422, str(problem)) from None
    row = repo(settings, "user_skills", claims.user_id).insert({
        "id": f"u-{uuid.uuid4().hex[:12]}", "name": body.name.strip(), "triggers": triggers,
        "allowed_tools": body.allowed_tools, "instructions": body.instructions, "summary": body.summary,
        "enabled": True,
    })
    _reload_live_skills(settings, claims.user_id)
    return user_skill(row).item()


@skills_router.patch("/{skill_id}", response_model=SkillItem)
def update_skill(
    skill_id: Id, body: SkillUpdate, settings: Annotated[Settings, Depends(get_settings)], claims: Claims,
    skills: Annotated[list, Depends(get_skills)],
) -> SkillItem:
    current = next((s for s in skills if s.id == skill_id), None)
    if current is None:
        raise HTTPException(404, "Skill not found")
    if current.builtin:
        raise HTTPException(409, "Built-in skills can't be changed. Make a copy instead")
    changes = body.model_dump(exclude_none=True)
    try:
        if "triggers" in changes or "allowed_tools" in changes or "name" in changes:
            others = [s for s in skills if s.id != skill_id]
            changes["triggers"] = check_user_skill(
                changes.get("name", current.name), changes.get("triggers", current.triggers),
                changes.get("allowed_tools", current.allowed_tools), others,
            )
    except SkillProblem as problem:
        raise HTTPException(422, str(problem)) from None
    row = repo(settings, "user_skills", claims.user_id).update(skill_id, changes)
    if row is None:
        raise HTTPException(404, "Skill not found")
    _reload_live_skills(settings, claims.user_id)
    return user_skill(row).item()


@skills_router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: Id, settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> Response:
    if not repo(settings, "user_skills", claims.user_id).delete(skill_id):
        raise HTTPException(404, "Skill not found")  # built-ins are files: never here
    _reload_live_skills(settings, claims.user_id)
    return Response(status_code=204)


@skills_router.post("/{skill_id}/run", response_model=SkillRunAccepted, status_code=202)
def run_skill(
    skill_id: Id, found: Claims, skills: Annotated[list, Depends(get_skills)]
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
