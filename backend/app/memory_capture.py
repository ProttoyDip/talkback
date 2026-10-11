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


# Correction-aware memory (plan P4). A "slot" is the thing a memory is about,
# so a newer memory about the same thing replaces the older one instead of
# piling up next to it ("I live in Rome now" replaces "I live in Lisbon").
SLOTS = [
    (re.compile(r"\b(?:home ?city|hometown) is\b|\bi live in\b|\bi(?:'m| am) (?:from|based in)\b|\bi moved to\b", re.I), "home"),
    (re.compile(r"\bcall me\b|\bmy name is\b", re.I), "name"),
    (re.compile(r"\b(?:celsius|fahrenheit|metric|imperial)\b", re.I), "units"),
    (re.compile(r"\b(?:short|long|brief|detailed) answers\b", re.I), "answer_length"),
    (re.compile(r"\bi (?:start|finish|work)\b.*(?:\d|\b(?:morning|evening|noon)\b)", re.I), "work_hours"),
]
FAVOURITE = re.compile(r"\bmy favou?rite ([a-z]+(?: [a-z]+)?) is\b", re.I)
MY_THING = re.compile(r"\bmy ([a-z]+(?: [a-z]+)?) is\b", re.I)
CORRECTION = re.compile(
    r"\b(?:actually|instead|no longer|not anymore|any more|changed my mind|now|these days|correction)\b", re.I
)
SAY_IT = re.compile(r"^\s*(?:(?:no|actually|wait|sorry)[,\s]+)*(?:i|my|call me)\b", re.I)


def slot_of(text: str) -> str | None:
    """What a memory is about, if TalkBack can tell (home, name, units...)."""
    for pattern, slot in SLOTS:
        if pattern.search(text):
            return slot
    if match := FAVOURITE.search(text):
        return f"favourite:{match.group(1).lower()}"
    if match := MY_THING.search(text):
        return f"my:{match.group(1).lower()}"
    return None


def extract_correction(utterance: str) -> tuple[str, MemoryKind, str] | None:
    """ "Actually, I live in Rome now": a correction of something already
    remembered, said without "remember that". Returns text, kind and slot;
    the caller replaces a memory only if one with that slot exists."""
    text = utterance.strip()
    if not CORRECTION.search(text) or not SAY_IT.match(text) or len(text) > MAX_LENGTH:
        return None
    slot = slot_of(text)
    if slot is None:
        return None
    cleaned = re.sub(r"^\s*(?:(?:no|actually|wait|sorry)[,\s]+)+", "", text, flags=re.I).strip(" .!,")
    if len(cleaned) < 3:
        return None
    kind: MemoryKind = "preference" if PREFERENCE.search(cleaned) else "fact"
    return cleaned[0].upper() + cleaned[1:], kind, slot
