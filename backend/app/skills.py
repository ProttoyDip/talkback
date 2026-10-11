"""Skills (plan.md X5): short instructions plus the tools they may use.

Each skill is a JSON file in backend/skills. A skill can use only the tools in
its allowed_tools list, and that is enforced where tools run, not only in the
prompt (SECURITY.md T5).
"""

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .protocol import Id, SkillItem, ToolName

log = logging.getLogger("talkback.skills")


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Id
    name: str = Field(min_length=1, max_length=60)
    triggers: list[str] = Field(min_length=1, max_length=10)
    allowed_tools: list[ToolName]
    instructions: str = Field(min_length=1, max_length=2000)
    # One plain sentence for the Skills panel: what it does and what to say.
    summary: str | None = Field(default=None, max_length=200)

    # False for a skill the user made (plan P5); built-ins ship as files.
    builtin: bool = True
    enabled: bool = True

    def item(self) -> SkillItem:
        return SkillItem(
            id=self.id, name=self.name, triggers=self.triggers, allowed_tools=self.allowed_tools,
            summary=self.summary, builtin=self.builtin, enabled=self.enabled,
            instructions=None if self.builtin else self.instructions,
        )


# Your own skills (plan P5): stored per user, checked like the built-ins.
MAX_USER_SKILLS = 20
# Words that already mean something in a conversation; never a trigger.
RESERVED_TRIGGERS = frozenset({
    "yes", "yeah", "okay", "stop", "cancel", "never mind", "remember", "remember that", "forget it",
    "go ahead", "wait", "help",
})
# A skill may use these tools (never skill_run: a skill does not start skills).
SKILL_TOOLS = frozenset({
    "weather", "web_search", "memory_read", "memory_suggest", "memory_delete",
    "task_list", "task_add", "task_update", "task_delete",
    "calendar_list", "calendar_add", "calendar_update", "calendar_delete", "reminder_set", "reminder_update",
})


class SkillProblem(ValueError):
    """A user skill that cannot be saved; the message is shown to the user."""


def clean_triggers(triggers: list[str]) -> list[str]:
    cleaned = []
    for trigger in triggers:
        phrase = " ".join(trigger.lower().split())
        if len(phrase) < 4 or phrase in RESERVED_TRIGGERS:
            raise SkillProblem(f"“{trigger}” can't start a skill. Use a phrase of 4 or more letters.")
        if phrase not in cleaned:
            cleaned.append(phrase)
    return cleaned


def check_user_skill(name: str, triggers: list[str], tools: list[str], others: list[Skill]) -> list[str]:
    """Clean triggers, or raise SkillProblem with a plain reason."""
    cleaned = clean_triggers(triggers)
    if unknown := set(tools) - SKILL_TOOLS:
        raise SkillProblem(f"A skill can't use {', '.join(sorted(unknown))}.")
    taken = {t.lower() for skill in others for t in skill.triggers}
    if clash := [t for t in cleaned if t in taken]:
        raise SkillProblem(f"“{clash[0]}” already starts another skill.")
    if not name.strip():
        raise SkillProblem("Give the skill a name.")
    return cleaned


def user_skill(row: dict) -> Skill:
    return Skill(
        id=row["id"], name=row["name"], triggers=row["triggers"], allowed_tools=row["allowed_tools"],
        instructions=row["instructions"], summary=row.get("summary"), builtin=False, enabled=bool(row["enabled"]),
    )


def load_skills(directory: str | Path) -> list[Skill]:
    skills: list[Skill] = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            skills.append(Skill.model_validate_json(path.read_text(encoding="utf-8")))
        except (ValidationError, ValueError, OSError):
            log.warning("skill file skipped", extra={"event": path.name})
    ids = [s.id for s in skills]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate skill id")
    return skills


def match_trigger(text: str, skills: list[Skill]) -> Skill | None:
    """The skill whose trigger phrase the user said, if any."""
    lowered = text.lower()
    for skill in skills:
        for trigger in skill.triggers:
            if re.search(rf"\b{re.escape(trigger.lower())}\b", lowered):
                return skill
    return None
