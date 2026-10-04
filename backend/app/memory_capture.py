"""Saves memories from what the user said (SECURITY.md T1).

A memory is written only when the user's own words ask for it ("remember
that I prefer Celsius"). The text comes from the transcript by a fixed rule,
never from model output or a tool result, so a web page cannot plant one.
"""

import re

from .protocol import MemoryKind

ASK = re.compile(
    r"^\s*(?:(?:please|hey|okay|ok|and)[,\s]+)*(?:remember|don't forget|do not forget|make a note|note)"
    r"(?:\s+that)?[,:\s]+(?P<what>.{3,})$",
    re.IGNORECASE | re.DOTALL,
)
PREFERENCE = re.compile(r"\b(?:prefer|like|love|hate|favou?rite|always|never|call me|speak|talk)\b", re.IGNORECASE)
REMINDER = re.compile(r"\b(?:remind me|reminder|tomorrow|tonight|next week|on monday|on tuesday|on wednesday|on thursday|on friday)\b", re.IGNORECASE)

MAX_LENGTH = 500


def extract_memory(utterance: str) -> tuple[str, MemoryKind] | None:
    """The memory text and kind if the user asked TalkBack to remember something."""
    match = ASK.match(utterance.strip())
    if match is None:
        return None
    text = match.group("what").strip(" .!,")
    if len(text) < 3:
        return None
    kind: MemoryKind = "reminder" if REMINDER.search(text) else "preference" if PREFERENCE.search(text) else "fact"
    return text[:MAX_LENGTH], kind
