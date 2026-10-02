"""Runs one scenario through the real VAD and decision code."""

import math
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.turn_taking import BargeInDecider, EnergyVad, heard_split  # noqa: E402

from scenarios import ASR_DELAY_MS, WORDS, Scenario  # noqa: E402

FRAME_MS = 20


def frame(amplitude: int) -> bytes:
    return array("h", (int(amplitude * math.sin(i / 3)) for i in range(320))).tobytes()


@dataclass(frozen=True)
class Outcome:
    interrupted: bool
    stop_after_ms: int | None  # user speech time until the assistant stops
    heard: str
    unheard: str
    trim_error_words: int = 0  # reported position vs the true one


def run(scenario: Scenario) -> Outcome:
    vad, decider = EnergyVad(), BargeInDecider()
    for _ in range(30):  # 600 ms of room noise first
        vad.process(frame(0))
    for step in range(scenario.speech_ms // FRAME_MS + 15):
        speaking = step * FRAME_MS < scenario.speech_ms
        state = vad.process(frame(5000 if speaking else 0))
        # The recognizer shows words once it has had ASR_DELAY_MS of speech.
        interim = scenario.text if state.speech_ms >= ASR_DELAY_MS else ""
        if state.is_speech and decider.update(state.speech_ms, interim) == "interrupt":
            # The playback position is the one the browser last reported.
            true_s = scenario.played_s + state.speech_ms / 1000
            reported_s = int(true_s * 10) / 10  # the browser reports every 100 ms
            heard, unheard = heard_split(WORDS, reported_s)
            truth, _ = heard_split(WORDS, true_s)
            error = abs(len(heard.split()) - len(truth.split()))
            return Outcome(True, state.speech_ms, heard, unheard, error)
    return Outcome(False, None, "", "")
