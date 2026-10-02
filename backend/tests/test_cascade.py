"""Plan B (X12): LLM provider order, the cascade engine and the gateway bridge.
Offline: fake speech, mocked HTTP. No keys needed."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.cascade_engine import CascadeEngine
from app.config import Settings
from app.engines import EngineChoice, create_engine, get_engine_factory
from app.llm import LlmClient, LlmProvider, LlmUnavailable, providers_from_settings
from app.main import app
from app.speech import Speech, estimate_word_times
from app.voice_engine import (
    AssistantAudio,
    AssistantWord,
    ModelInUse,
    SessionContext,
    StateChanged,
    TurnEnded,
    UserTranscript,
)

from .conftest import ORIGIN, SECRET


def sse(*pieces: str) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n" for p in pieces]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def provider(id_: str, primary: bool) -> LlmProvider:
    return LlmProvider(id=id_, base_url=f"https://{id_}.test/v1", model=f"{id_}-model",
                       api_key=SecretStr(f"key-{id_}"), primary=primary, extra_body={"x": id_})


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakeSTT:
    """Says `utterance` (partial, then final) when the first audio frame arrives."""

    def __init__(self, utterance: str = "What does full-duplex mean?") -> None:
        self.utterance = utterance
        self.on_result = None
        self.pushed = 0
        self.closed = False

    def start(self, on_result, on_error) -> None:
        self.on_result = on_result

    def push(self, frame: bytes) -> None:
        self.pushed += 1
        if self.pushed == 1:
            words = self.utterance.split()
            self.on_result(" ".join(words[:2]), False)
            self.on_result(self.utterance, True)

    def close(self) -> None:
        self.closed = True


class FakeTTS:
    """20 ms of audio per word, with estimated word timing."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> Speech:
        self.spoken.append(text)
        samples = int(22_050 * 0.02) * len(text.split())
        return Speech(pcm=b"\x01\x00" * samples, words=estimate_word_times(text, samples / 22_050))


# LLM providers


def test_providers_need_keys_and_put_nebius_first():
    settings = Settings(_env_file=None, nebius_api_key="n", openrouter_api_key="o")
    assert [p.id for p in providers_from_settings(settings)] == ["nebius", "openrouter"]
    only_backup = Settings(_env_file=None, openrouter_api_key="o")
    assert [p.id for p in providers_from_settings(only_backup)] == ["openrouter"]
    assert providers_from_settings(Settings(_env_file=None)) == []


def test_thinking_is_turned_off_for_voice():
    settings = Settings(_env_file=None, nebius_api_key="n", openrouter_api_key="o")
    by_id = {p.id: p for p in providers_from_settings(settings)}
    assert by_id["openrouter"].extra_body == {"reasoning": {"enabled": False}}
    assert by_id["nebius"].extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


async def collect(client: LlmClient) -> tuple[str, list[str]]:
    used: list[str] = []
    text = "".join([p async for p in client.stream([{"role": "user", "content": "hi"}], lambda p: used.append(p.id))])
    return text, used


@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_failing_primary_switches_to_backup(status):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, json.loads(request.content)))
        if request.url.host == "nebius.test":
            return httpx.Response(status, json={"error": "nope"})
        return httpx.Response(200, content=sse("Hello", " there."))

    async def run():
        async with mock_client(handler) as http:
            return await collect(LlmClient([provider("nebius", True), provider("openrouter", False)], http))

    text, used = asyncio.run(run())
    assert text == "Hello there."
    assert used == ["openrouter"]
    assert [host for host, _ in seen] == ["nebius.test", "openrouter.test"]
    assert seen[1][1]["stream"] is True and seen[1][1]["x"] == "openrouter"


def test_no_provider_gives_a_safe_message_without_keys():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async def run():
        async with mock_client(handler) as http:
            return await collect(LlmClient([provider("nebius", True)], http))

    with pytest.raises(LlmUnavailable) as error:
        asyncio.run(run())
    assert "key-" not in str(error.value)


# Cascade engine


async def run_turn(engine: CascadeEngine, stt: FakeSTT) -> list:
    await engine.start(SessionContext("s1"))
    await engine.send_audio(b"\x00" * 640)
    events = []
    async for event in engine.events():
        events.append(event)
        if isinstance(event, TurnEnded):
            break
    await engine.close()
    return events


def test_a_spoken_question_gets_a_spoken_answer():
    stt, tts = FakeSTT(), FakeTTS()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse("It means both sides ", "talk at once. ", "Like a phone **call**."))

    async def run():
        async with mock_client(handler) as http:
            engine = CascadeEngine(stt, tts, LlmClient([provider("openrouter", False)], http))
            return engine, await run_turn(engine, stt)

    engine, events = asyncio.run(run())
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "ModelInUse" and events[0].role == "voice" and events[0].provider == "nvidia"
    assert [e.state for e in events if isinstance(e, StateChanged)] == ["listening", "thinking", "assistant_speaking"]
    assert [(e.text, e.final) for e in events if isinstance(e, UserTranscript)] == [
        ("What does", False), ("What does full-duplex mean?", True)]
    planner = [e for e in events if isinstance(e, ModelInUse) and e.role == "planner"]
    assert planner[0].provider == "openrouter" and planner[0].backup is True

    # Sentence by sentence, markdown removed before speaking.
    assert tts.spoken == ["It means both sides talk at once.", "Like a phone call."]
    words = [e for e in events if isinstance(e, AssistantWord)]
    assert [w.word for w in words][-2:] == ["phone", "call."]
    starts = [w.start_s for w in words]
    assert starts == sorted(starts)  # second sentence continues after the first
    audio = b"".join(e.pcm for e in events if isinstance(e, AssistantAudio))
    assert len(audio) // 2 == int(22_050 * 0.02) * 11  # 11 words, 20 ms each
    assert events[-1].text == "It means both sides talk at once. Like a phone call."
    assert engine.history[-1]["content"] == events[-1].text
    assert stt.closed


def test_interrupt_keeps_only_heard_words_in_history():
    stt, tts = FakeSTT(), FakeTTS()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse("First part. ", "Second part."))

    async def run():
        async with mock_client(handler) as http:
            engine = CascadeEngine(stt, tts, LlmClient([provider("openrouter", False)], http))
            events = await run_turn(engine, stt)
            await engine.interrupt(events[-1].message_id, "First part.")
            return engine

    engine = asyncio.run(run())
    assert engine.history[-1]["content"] == "First part."


def test_language_model_failure_is_reported_not_crashed():
    stt, tts = FakeSTT(), FakeTTS()

    async def run():
        async with mock_client(lambda r: httpx.Response(503)) as http:
            engine = CascadeEngine(stt, tts, LlmClient([provider("nebius", True)], http))
            return await run_turn(engine, stt)

    events = asyncio.run(run())
    problems = [e for e in events if type(e).__name__ == "EngineProblem"]
    assert problems and "isn't reachable" in problems[0].message
    assert tts.spoken == []


# Engine selection and the gateway bridge


def test_cascade_without_nvidia_key_explains_what_is_missing():
    choice = create_engine(Settings(_env_file=None, voice_engine="cascade"))
    assert choice.engine is None and "NVIDIA_API_KEY" in choice.problem


def test_gateway_streams_a_full_answer(client, settings):
    stt, tts = FakeSTT(), FakeTTS()
    holder = {}

    def factory(_settings: Settings) -> EngineChoice:
        http = mock_client(lambda r: httpx.Response(200, content=sse("Both sides talk. ", "At once.")))
        holder["engine"] = CascadeEngine(stt, tts, LlmClient([provider("nebius", True)], http))
        return EngineChoice(holder["engine"], http=http)

    app.dependency_overrides[get_engine_factory] = lambda: factory
    token = client.post("/api/session").json()["token"]
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        ws.send_bytes(b"\x00" * 640)
        received, binary, spoke = [], 0, False
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                binary += 1
                continue
            event = json.loads(message["text"])
            received.append(event)
            spoke = spoke or event == {"type": "state", "state": "assistant_speaking"}
            if spoke and event == {"type": "state", "state": "idle"}:
                break

    types = [e["type"] for e in received]
    assert received[0] == {"type": "state", "state": "idle"}
    assert {"type": "model.active", "role": "voice", "provider": "nvidia",
            "model": "Parakeet + Magpie TTS", "backup": False} in received
    assert {"type": "model.active", "role": "planner", "provider": "nebius",
            "model": "nebius-model", "backup": False} in received
    user_final = [e for e in received if e["type"] == "transcript.delta" and e["speaker"] == "user" and e["final"]]
    assert user_final[0]["text"] == "What does full-duplex mean?"

    chunks = [e for e in received if e["type"] == "audio.chunk"]
    assert binary == len(chunks) > 0
    assert [c["seq"] for c in chunks] == list(range(len(chunks)))

    words = [e for e in received if e["type"] == "transcript.delta" and e["speaker"] == "assistant"]
    assert "".join(w["text"] for w in words) == "Both sides talk. At once."
    assert words[-1]["final"] is True
    # The turn ends only after its last caption.
    assert types.index("transcript.delta") < len(types) - 1
    assert received[-1] == {"type": "state", "state": "idle"}
