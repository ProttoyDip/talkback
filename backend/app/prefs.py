"""User settings kept on the server (docs/architecture.md 3.2, SECURITY.md T4).

A small JSON file next to the memory database. Everything defaults to the
private choice: recordings off, transcripts out of logs, all tools on.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("talkback.prefs")


@dataclass
class Prefs:
    tools: dict[str, bool] = field(default_factory=dict)  # missing means on
    save_recordings: bool = False
    transcripts_in_logs: bool = False
    interrupt_sensitivity: str = "normal"  # low, normal or high
    answer_length: str = "normal"  # short, normal or detailed
    planner_model: str = ""  # a ModelOption id; empty means the default order
    providers: dict[str, bool] = field(default_factory=dict)  # missing means on

    def tool_enabled(self, name: str) -> bool:
        return self.tools.get(name, True)

    def provider_enabled(self, provider_id: str) -> bool:
        return self.providers.get(provider_id, True)


def _choice(value: object, allowed: tuple[str, ...]) -> str:
    return value if isinstance(value, str) and value in allowed else "normal"


class PrefsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock = threading.Lock()

    @staticmethod
    def from_raw(raw: object) -> Prefs:
        """Settings from stored JSON. Anything unexpected falls back to the private defaults."""
        try:
            assert isinstance(raw, dict)
            return Prefs(
                tools={str(k): bool(v) for k, v in dict(raw.get("tools", {})).items()},
                save_recordings=bool(raw.get("save_recordings", False)),
                transcripts_in_logs=bool(raw.get("transcripts_in_logs", False)),
                interrupt_sensitivity=_choice(raw.get("interrupt_sensitivity"), ("low", "normal", "high")),
                answer_length=_choice(raw.get("answer_length"), ("short", "normal", "detailed")),
                planner_model=str(raw.get("planner_model", ""))[:100],
                providers={str(k): bool(v) for k, v in dict(raw.get("providers", {})).items()},
            )
        except (AssertionError, ValueError, TypeError, AttributeError):
            return Prefs()

    def load(self) -> Prefs:
        try:
            return self.from_raw(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return Prefs()

    def save(self, prefs: Prefs) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(prefs)), encoding="utf-8")
