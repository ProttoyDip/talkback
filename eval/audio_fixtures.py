"""Spoken test utterances for the end-to-end evaluation (plan P9).

Made once with NVIDIA Magpie TTS (the same voice service TalkBack uses) as
16 kHz mono WAVs, the browser's microphone format, and cached in
eval/fixtures/ (not committed; run this file to make them).

    backend/.venv/Scripts/python eval/audio_fixtures.py
"""

import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

FIXTURES = ROOT / "fixtures"
RATE = 16_000
VOICE = "Magpie-Multilingual.EN-US.Aria"  # not TalkBack's own voice, as a user would be

UTTERANCES = {
    "weather_lisbon": "What's the weather in Lisbon today?",
    "weather_tokyo": "What's the weather like in Tokyo right now?",
    "capital_question": "What is the capital of Australia?",
    "long_answer": "Tell me about the history of Lisbon in a few sentences.",
    "explain_tides": "Can you explain how ocean tides work?",
    "wait_stop": "Wait, stop.",
    "hold_on": "Hold on a second.",
    # Magpie draws "Mm-hm" out to two 600 ms hums, longer than people say
    # it; "Uh-huh" comes out at a natural 300 ms.
    "uh_huh": "Uh-huh.",
    "remind_nine": "Remind me to call mom tomorrow at nine in the morning.",
    "no_make_it_ten": "No wait, make it ten.",
    "never_mind": "Never mind.",
    "yes": "Yes.",
    "no": "No.",
}


def path(name: str) -> Path:
    return FIXTURES / f"{name}.wav"


def pcm(name: str) -> bytes:
    with wave.open(str(path(name))) as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


def main() -> int:
    import riva.client

    from app.config import Settings
    from app.speech.nvidia import _auth

    settings = Settings()
    if not settings.nvidia_api_key.get_secret_value():
        print("NVIDIA_API_KEY is not set in backend/.env")
        return 1
    service = riva.client.SpeechSynthesisService(_auth(settings.riva_server, settings.tts_function_id, settings.nvidia_api_key))
    FIXTURES.mkdir(exist_ok=True)
    for name, text in UTTERANCES.items():
        if path(name).exists():
            continue
        response = service.synthesize(
            text, voice_name=VOICE, language_code="en-US",
            encoding=riva.client.AudioEncoding.LINEAR_PCM, sample_rate_hz=RATE,
        )
        with wave.open(str(path(name)), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(response.audio))
        print(f"made {name}.wav ({len(response.audio) / 2 / RATE:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
