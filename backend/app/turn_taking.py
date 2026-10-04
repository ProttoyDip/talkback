"""Turn-taking (plan.md X2, architecture.md 4).

Pure logic, no I/O, so every rule is unit-tested without audio:
- EnergyVad: speech or silence for each 20 ms frame, and how long the
  current speech has lasted.
- BargeInDecider: when speech over the assistant is a real interruption and
  when it is a backchannel ("mm-hm") that must not stop it.
- heard_split: from the playback position, which assistant words the user
  actually heard.
- Text helpers for the conversation controller: filler words, hesitation,
  unfinished sentences, reactions.

The VAD is energy based with an adaptive noise floor. It sits behind the same
frame interface a Silero model would use, so Silero can replace it later.
"""

import re
from array import array
from dataclasses import dataclass

FRAME_MS = 20

# architecture.md 4: speech shorter than this is ignored; a backchannel is a
# short sound from the word list.
MIN_SPEECH_MS = 250
BACKCHANNEL_MAX_MS = 600


@dataclass(frozen=True)
class VadState:
    is_speech: bool
    speech_ms: int  # length of the current run of speech; 0 in silence


class EnergyVad:
    """Frame-by-frame speech detector with hysteresis and a noise floor."""

    def __init__(self, min_level: float = 350.0, floor_factor: float = 3.5, hangover_ms: int = 200) -> None:
        self.min_level = min_level
        self.floor_factor = floor_factor
        self.hangover_frames = hangover_ms // FRAME_MS
        self.floor = 100.0
        self.speech_frames = 0
        self.quiet_run = 0
        self.active = False

    @staticmethod
    def rms(frame: bytes) -> float:
        samples = array("h")
        samples.frombytes(frame[: len(frame) // 2 * 2])
        if not samples:
            return 0.0
        return (sum(s * s for s in samples) / len(samples)) ** 0.5

    def process(self, frame: bytes) -> VadState:
        level = self.rms(frame)
        threshold = max(self.min_level, self.floor * self.floor_factor)
        if level >= threshold:
            # A dip inside the speech counts once the speech resumes.
            self.speech_frames += 1 + self.quiet_run
            self.quiet_run = 0
            self.active = True
        elif self.active:
            self.quiet_run += 1
            if self.quiet_run > self.hangover_frames:
                self.active = False
                self.speech_frames = 0
                self.quiet_run = 0
        if not self.active:
            self.floor = 0.95 * self.floor + 0.05 * level  # learn the room noise
        # Trailing quiet frames keep is_speech on but do not lengthen the speech.
        return VadState(self.active, self.speech_frames * FRAME_MS)


# Short sounds that mean "keep going". "yes" and "no" are not here: they can
# be answers or corrections.
BACKCHANNELS = frozenset(
    {
        "mm", "mmm", "mhm", "mm-hm", "mmhm", "uh-huh", "uhhuh", "hmm", "hm",
        "yeah", "yep", "yup", "ok", "okay", "right", "sure", "alright", "all right",
        "i see", "got it", "cool", "great", "nice", "oh", "ah", "wow",
    }
)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+(?:-[a-z']+)*", text.lower())


def is_backchannel(text: str) -> bool:
    words = _words(text)
    if not words or len(words) > 2:
        return False
    return " ".join(words) in BACKCHANNELS or all(w in BACKCHANNELS for w in words)


# Settings > Interruptions: (minimum speech ms, backchannel limit ms).
SENSITIVITY = {
    "low": (400, 800),  # noisy rooms: needs longer speech to stop TalkBack
    "normal": (MIN_SPEECH_MS, BACKCHANNEL_MAX_MS),
    "high": (180, 450),  # quiet rooms: stops sooner
}


class BargeInDecider:
    """Decides while the assistant speaks. Call update() on every frame."""

    def __init__(self, min_speech_ms: int = MIN_SPEECH_MS, backchannel_max_ms: int = BACKCHANNEL_MAX_MS) -> None:
        self.min_speech_ms = min_speech_ms
        self.backchannel_max_ms = backchannel_max_ms

    @classmethod
    def for_sensitivity(cls, level: str) -> "BargeInDecider":
        return cls(*SENSITIVITY.get(level, SENSITIVITY["normal"]))

    def update(self, speech_ms: int, interim_text: str) -> str:
        """Returns "none", "overlap" (user talks, undecided) or "interrupt"."""
        if speech_ms < self.min_speech_ms:
            return "none"
        text = interim_text.strip()
        if text and not is_backchannel(text):
            return "interrupt"  # real words: stop now
        if speech_ms >= self.backchannel_max_ms:
            return "interrupt"  # too long to be a backchannel
        return "overlap"


def heard_split(words: list[tuple[str, float, float]], played_s: float) -> tuple[str, str]:
    """Split an assistant message at the playback position.

    words: (word, start_s, end_s) in message time. A word counts as heard when
    at least half of it was played. Returns (heard_text, unheard_text).
    """
    heard: list[str] = []
    unheard: list[str] = []
    for word, start_s, end_s in words:
        (heard if (start_s + end_s) / 2 <= played_s and not unheard else unheard).append(word)
    return " ".join(heard), " ".join(unheard)


# Conversation controller: text rules (plan.md X2, English).

FILLER = re.compile(r"\b(?:u+m+|u+h+|e+r+m?|a+h+|h+m+|m+h?m+|mm+)\b[,.…]*", re.IGNORECASE)
REPEATED_WORD = re.compile(r"\b(\w+)(?:[,\s]+\1\b)+", re.IGNORECASE)
# A turn ending on one of these is probably not finished.
DANGLING = frozenset(
    "and but so because or then the a an to of with that which if when while my i is are was were "
    "for in on at from about like also plus".split()
)


def strip_fillers(text: str) -> str:
    """Remove "umm"/"ahh" and stutters ("I I want" -> "I want")."""
    without = FILLER.sub(" ", text)
    without = REPEATED_WORD.sub(r"\1", without)
    return " ".join(without.split())


def is_filler_only(text: str) -> bool:
    return not _words(strip_fillers(text))


def looks_incomplete(text: str) -> bool:
    """True when the thought seems to continue: trailing comma, dash, ellipsis
    or a connecting word."""
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.endswith((",", "-", "–", "—", "…", "...", ":", ";")):
        return True
    if FILLER.fullmatch(stripped.split()[-1].lower()):
        return True
    words = _words(stripped)
    return bool(words) and words[-1] in DANGLING and not stripped.endswith(("?", "!"))
