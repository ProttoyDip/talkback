"""Speech-to-text and text-to-speech adapters for the cascade engine (plan B)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

SAMPLE_RATE_OUT = 22_050  # TTS output, matches the playback contract


@dataclass(frozen=True)
class Speech:
    """Synthesized audio (PCM16 mono, 22.05 kHz) and per-word timing in seconds."""

    pcm: bytes
    words: list[tuple[str, float, float]] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / SAMPLE_RATE_OUT


class SpeechToText(Protocol):
    def start(self, on_result: Callable[[str, bool], None], on_error: Callable[[str], None]) -> None:
        """Begin streaming. Callbacks may be called from another thread."""

    def push(self, frame: bytes) -> None:
        """One 20 ms PCM16 frame at 16 kHz. Must not block."""

    def close(self) -> None: ...


class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> Speech: ...


def estimate_word_times(text: str, duration_s: float) -> list[tuple[str, float, float]]:
    """Fallback when the TTS gives no word timing: spread words over the audio
    in proportion to their length."""
    words = text.split()
    total = sum(len(w) + 1 for w in words) or 1
    times, cursor = [], 0.0
    for w in words:
        span = duration_s * (len(w) + 1) / total
        times.append((w, cursor, cursor + span))
        cursor += span
    return times
