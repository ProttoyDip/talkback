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

    def item(self) -> SkillItem:
        return SkillItem(id=self.id, name=self.name, triggers=self.triggers, allowed_tools=self.allowed_tools)


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
