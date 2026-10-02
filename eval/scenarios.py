"""Fifty scripted turn-taking scenarios (plan.md X8).

Each scenario describes what the user does while TalkBack is speaking. The
evaluation feeds synthetic 20 ms frames through the same VAD and decision
code the gateway uses, so the numbers are repeatable and need no keys.

What this measures: the turn-taking decision. What it does not measure:
speech-recognition delay, model delay or network delay. Those need the live
engine (run the same scenarios with real audio once X7 or plan B is running).
"""

from dataclasses import dataclass

# The assistant sentence, 0.35 s per word, as in the demo script.
ASSISTANT = (
    "Tomorrow in Lisbon looks mild around twenty degrees with a low chance of rain "
    "so bring a light jacket for the evening"
).split()
WORD_S = 0.35
WORDS = [(w, i * WORD_S, (i + 1) * WORD_S) for i, w in enumerate(ASSISTANT)]

# How late the recognizer shows its first words after speech starts.
ASR_DELAY_MS = 300


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: str  # "interrupt", "backchannel" or "blip"
    speech_ms: int  # how long the user talks
    text: str  # what the recognizer hears
    played_s: float  # how much of the assistant message had played when the user started


def build() -> list[Scenario]:
    scenarios: list[Scenario] = []
    corrections = ["wait", "no that's wrong", "actually I meant Porto", "stop", "sorry what"]
    for i, played in enumerate([0.4, 0.9, 1.5, 2.2, 3.0, 3.6, 4.1, 4.8, 5.5, 6.0]):
        for j, text in enumerate(corrections[:2] if i % 2 else corrections[2:4]):
            scenarios.append(Scenario(f"interrupt {i}.{j}", "interrupt", 900, text, played))
    for i, text in enumerate(["mm-hm", "yeah", "okay", "uh-huh", "right", "I see", "got it", "hmm", "cool", "sure"]):
        for j, ms in enumerate([300, 450]):
            scenarios.append(Scenario(f"backchannel {i}.{j}", "backchannel", ms, text, 1.0 + i * 0.4))
    for i, ms in enumerate([60, 100, 140, 180, 220]):
        scenarios.append(Scenario(f"blip {i}", "blip", ms, "", 1.0 + i * 0.5))
    # Real words that start with a backchannel word must still interrupt.
    for i, text in enumerate(["yeah but what about Porto", "okay stop there", "right so tell me about rain",
                              "mm wait", "hmm no that is wrong"]):
        scenarios.append(Scenario(f"mixed {i}", "interrupt", 1200, text, 1.2 + i * 0.7))
    return scenarios
