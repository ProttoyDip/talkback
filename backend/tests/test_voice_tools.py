"""X13: tools in the voice engine (weather). Real tool bridge and weather tool,
mocked HTTP for Nemotron and Open-Meteo. Offline, no keys."""

import asyncio
import json

import httpx
from pydantic import SecretStr

from app.cascade_engine import CascadeEngine
from app.config import Settings
from app.engines import EngineChoice, get_engine_factory
from app.llm import LlmClient, LlmProvider, ToolCalls
from app.main import app
from app.protocol import ToolStatus
from app.tool_bridge import ToolBridge
from app.tools import Tool, ToolResult
from app.tools.weather import WeatherArguments, weather_tool
from app.voice_engine import ProtocolEvent, SessionContext, StateChanged, TurnEnded

from .conftest import ORIGIN
from .test_cascade import FakeSTT, FakeTTS, sse

PROVIDER = LlmProvider(id="nebius", base_url="https://llm.test/v1", model="m",
                       api_key=SecretStr("k"), primary=True)


def tool_call_sse(arguments: str, name: str = "weather") -> bytes:
    """A streamed tool call, split across chunks like real providers do."""
    half = len(arguments) // 2
    chunks = [
        {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": name, "arguments": ""}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": arguments[:half]}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": arguments[half:]}}]},
    ]
    body = "".join(f"data: {json.dumps({'choices': [{'delta': c}]})}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


class World:
    """Mock HTTP: Nemotron asks for the weather, then answers from the result."""

    def __init__(self, answer: str = "Tomorrow in Lisbon it will be about 21 degrees.") -> None:
        self.answer = answer
        self.llm_requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "llm.test":
            body = json.loads(request.content)
            self.llm_requests.append(body)
            if len(self.llm_requests) == 1:
                return httpx.Response(200, content=tool_call_sse('{"location": "Lisbon", "day": "tomorrow"}'))
            return httpx.Response(200, content=sse(self.answer))
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={"results": [{"name": "Lisbon", "latitude": 38.72, "longitude": -9.14}]})
        if request.url.host == "api.open-meteo.com":
            return httpx.Response(200, json={"daily": {
                "time": ["2026-10-02", "2026-10-03"],
                "temperature_2m_min": [15.2, 14.8], "temperature_2m_max": [24.1, 21.3],
                "precipitation_probability_max": [5, 60]}})
        return httpx.Response(404)


def make_engine(http: httpx.AsyncClient, tools: list[Tool] | None = None, filler_after: float = 0.7):
    tools = tools if tools is not None else [weather_tool(http)]
    return CascadeEngine(
        FakeSTT("What's the weather in Lisbon tomorrow?"), FakeTTS(), LlmClient([PROVIDER], http),
        bridge_factory=lambda sid, emit, say: ToolBridge(sid, tools, emit, say, filler_after=filler_after),
    )


async def one_turn(engine: CascadeEngine) -> list:
    await engine.start(SessionContext("s1"))
    await engine.send_audio(b"\x00" * 640)
    events = []
    async for event in engine.events():
        events.append(event)
        if isinstance(event, TurnEnded) and event.ends_turn:
            break
    await engine.close()
    return events


def test_streamed_tool_calls_are_reassembled_and_tools_are_offered():
    world = World()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world)) as http:
            client = LlmClient([PROVIDER], http)
            tools = [{"name": "weather", "description": "d", "parameters": {"type": "object"}}]
            return [p async for p in client.stream([{"role": "user", "content": "x"}], lambda p: None, tools=tools)]

    items = asyncio.run(run())
    assert len(items) == 1 and isinstance(items[0], ToolCalls)
    call = items[0].calls[0]
    assert (call.id, call.name, json.loads(call.arguments)) == ("call_1", "weather", {"location": "Lisbon", "day": "tomorrow"})
    sent = world.llm_requests[0]
    assert sent["tools"][0]["type"] == "function" and sent["tool_choice"] == "auto"


def test_weather_question_gets_a_spoken_forecast():
    world = World()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world)) as http:
            return await one_turn(make_engine(http))

    events = asyncio.run(run())
    states = [(e.state, e.tool) for e in events if isinstance(e, StateChanged)]
    assert ("tool", "weather") in states
    assert states.index(("tool", "weather")) < states.index(("assistant_speaking", None))

    statuses = [e.message for e in events if isinstance(e, ProtocolEvent) and isinstance(e.message, ToolStatus)]
    assert [s.status for s in statuses] == ["running", "done"]
    turn = events[-1]
    assert all(s.message_id == turn.message_id and s.name == "weather" for s in statuses)
    assert turn.text == "Tomorrow in Lisbon it will be about 21 degrees."

    # The forecast went back to Nemotron as untrusted data, with the call id.
    follow_up = world.llm_requests[1]["messages"]
    tool_message = next(m for m in follow_up if m["role"] == "tool")
    assert tool_message["tool_call_id"] == "call_1"
    assert "TOOL_RESPONSE" in tool_message["content"] and "untrusted" in tool_message["content"]
    assert "14.8 to 21.3 Celsius" in tool_message["content"]
    assert follow_up[-2]["tool_calls"][0]["function"]["name"] == "weather"


def test_slow_tool_says_a_filler_without_ending_the_turn():
    world = World()

    async def slow(arguments: WeatherArguments) -> list[ToolResult]:
        await asyncio.sleep(0.15)
        return [ToolResult("Lisbon", "https://open-meteo.com/", "21 Celsius")]

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(world)) as http:
            tool = Tool("weather", "Get a weather forecast.", WeatherArguments, slow, sensitive=False)
            return await one_turn(make_engine(http, [tool], filler_after=0.02))

    events = asyncio.run(run())
    filler = [e for e in events if isinstance(e, TurnEnded) and not e.ends_turn]
    assert [f.text for f in filler] == ["Let me check that."]
    assert events[-1].ends_turn and events[-1].text.startswith("Tomorrow in Lisbon")


def test_unknown_tool_from_the_model_is_refused_and_answered_in_words():
    world = World()
    original = world.__call__

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "llm.test" and not world.llm_requests:
            world.llm_requests.append(json.loads(request.content))
            return httpx.Response(200, content=tool_call_sse('{"cmd": "rm -rf /"}', name="shell"))
        return original(request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await one_turn(make_engine(http))

    events = asyncio.run(run())
    # No chip for a tool that does not exist; the model's next turn gets an error result.
    assert not [e for e in events if isinstance(e, ProtocolEvent)]
    assert "unknown_tool" in next(m for m in world.llm_requests[1]["messages"] if m["role"] == "tool")["content"]


def test_gateway_shows_the_tool_chip_and_state(client, settings):
    world = World()
    holder = {}

    def factory(_settings: Settings) -> EngineChoice:
        http = httpx.AsyncClient(transport=httpx.MockTransport(world))
        holder["engine"] = make_engine(http)
        return EngineChoice(holder["engine"], http=http)

    app.dependency_overrides[get_engine_factory] = lambda: factory
    token = client.post("/api/session").json()["token"]
    received = []
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        ws.send_bytes(b"\x00" * 640)
        spoke = False
        while True:
            message = ws.receive()
            if message.get("bytes") is not None:
                continue
            event = json.loads(message["text"])
            received.append(event)
            spoke = spoke or event == {"type": "state", "state": "assistant_speaking"}
            if spoke and event == {"type": "state", "state": "idle"}:
                break

    assert {"type": "state", "state": "tool", "tool": "weather"} in received
    chips = [e for e in received if e["type"] == "tool.status"]
    assert [c["status"] for c in chips] == ["running", "done"]
    words = [e for e in received if e["type"] == "transcript.delta" and e["speaker"] == "assistant"]
    assert {w["message_id"] for w in words} == {chips[0]["message_id"]}  # chip sits under the answer
    assert "".join(w["text"] for w in words) == "Tomorrow in Lisbon it will be about 21 degrees."
