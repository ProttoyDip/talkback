"""Plan P3: actions that follow the user's latest words, and typed turns."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.cascade_engine import CascadeEngine
from app.llm import ToolCallRequest, ToolCalls
from app.protocol import ToolConfirmRequest, ToolStatus
from app.tool_bridge import ToolBridge
from app.tools import Arguments, Tool, ToolResult
from app.turn_taking import classify_confirmation, is_cancel
from app.voice_engine import ProtocolEvent, SessionContext

from .conftest import ORIGIN
from .test_cascade import FakeSTT, FakeTTS
from .test_tool_bridge import request


# Spoken answers


@pytest.mark.parametrize(
    "said, answer, rest",
    [
        ("Yes.", "yes", ""),
        ("Go ahead!", "yes", ""),
        ("No.", "no", ""),
        ("Cancel that.", "no", ""),
        ("No, wait, Friday.", "no", "wait, Friday."),
        ("Cancel that, add milk instead", "no", "add milk instead"),
        ("Actually make it Friday", None, "Actually make it Friday"),
        ("yes and also tomorrow", None, "yes and also tomorrow"),  # not a plain yes: nothing runs
    ],
)
def test_only_a_plain_yes_approves(said, answer, rest):
    assert classify_confirmation(said) == (answer, rest)


def test_cancel_phrases_must_stand_alone():
    assert is_cancel("Never mind.") and is_cancel("Forget it")
    assert not is_cancel("Never mind the weather, what time is it?")


# The tool bridge


def sensitive_bridge(handler=None, **kwargs):
    handler = handler or AsyncMock(return_value=[ToolResult("Memory", "", "Memory deleted.")])
    emit = AsyncMock()
    tool = Tool("memory_delete", "Delete.", Arguments, handler, True, lambda args: "Delete the test memory?")
    return ToolBridge("session", [tool], emit, AsyncMock(), **kwargs), handler, emit


def statuses(emit) -> list[tuple[str, str | None]]:
    return [(c.args[0].status, c.args[0].reason) for c in emit.await_args_list if isinstance(c.args[0], ToolStatus)]


def test_cancelling_while_waiting_for_a_yes_reports_it_and_runs_nothing():
    bridge, handler, emit = sensitive_bridge()

    async def scenario():
        task = asyncio.create_task(bridge.execute(request(), "turn"))
        while not bridge.pending:
            await asyncio.sleep(0)
        bridge.cancel_reason = "stopped"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    handler.assert_not_called()
    assert statuses(emit) == [("cancelled", "stopped")]
    assert not bridge.pending


def test_an_approved_change_does_not_run_once_the_user_moved_on():
    bridge, handler, emit = sensitive_bridge()
    current = [True]

    async def event(message):
        if isinstance(message, ToolConfirmRequest):
            current[0] = False  # the user corrected the request while the card was open
            bridge.resolve(message.call_id, True)

    emit.side_effect = event
    asyncio.run(bridge.execute(request(), "turn", lambda: current[0]))
    handler.assert_not_called()
    assert statuses(emit) == [("cancelled", "superseded")]


def test_a_change_already_running_finishes_once_and_says_so():
    started, release = asyncio.Event(), asyncio.Event()
    runs = []

    async def slow_delete(args):
        runs.append(1)
        started.set()
        await release.wait()
        return [ToolResult("Memory", "", "Memory deleted.")]

    bridge, _, emit = sensitive_bridge(slow_delete, filler_after=10)

    async def event(message):
        if isinstance(message, ToolConfirmRequest):
            bridge.resolve(message.call_id, True)

    emit.side_effect = event

    async def scenario():
        task = asyncio.create_task(bridge.execute(request(), "turn"))
        await started.wait()
        task.cancel()  # the user interrupts mid-write
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(scenario())
    assert runs == [1]
    assert statuses(emit) == [("running", None), ("done", "already_done")]
    assert bridge.done_after_cancel == ["memory_delete"]  # the tool name, never model-written text


# The voice engine


class ScriptedLLM:
    """First a delete tool call; afterwards it answers in words."""

    def __init__(self) -> None:
        self.requests: list[list[dict]] = []

    async def stream(self, messages, on_provider, tools=None):
        self.requests.append(messages)
        if len(self.requests) == 1:
            yield ToolCalls([ToolCallRequest("c1", "memory_delete", "{}")])
        else:
            yield "Okay."


async def engine_with_pending_confirmation():
    llm = ScriptedLLM()
    handler = AsyncMock(return_value=[ToolResult("Memory", "", "Memory deleted.")])
    tool = Tool("memory_delete", "Delete.", Arguments, handler, True, lambda args: "Delete the test memory?")
    engine = CascadeEngine(
        FakeSTT(), FakeTTS(), llm,  # type: ignore[arg-type]
        bridge_factory=lambda sid, emit, filler: ToolBridge(sid, [tool], emit, filler),
    )
    await engine.start(SessionContext("s1"))
    engine.submit_text("Forget my home city.")
    while not (engine.bridge and engine.bridge.pending):
        await asyncio.sleep(0.01)
    return engine, handler, llm


def tool_events(engine) -> list[tuple[str, str | None]]:
    found = []
    while not engine.queue.empty():
        event = engine.queue.get_nowait()
        if isinstance(event, ProtocolEvent) and isinstance(event.message, ToolStatus):
            found.append((event.message.status, event.message.reason))
    return found


def test_a_spoken_yes_runs_the_change():
    async def scenario():
        engine, handler, _ = await engine_with_pending_confirmation()
        engine.submit_text("Yes.")
        await asyncio.wait_for(engine.reply, 2)
        await engine.close()
        return handler, tool_events(engine)

    handler, events = asyncio.run(scenario())
    handler.assert_awaited_once()
    assert ("done", None) in events


def test_no_wait_declines_and_answers_the_correction_instead():
    async def scenario():
        engine, handler, llm = await engine_with_pending_confirmation()
        engine.submit_text("No, wait, keep it and tell me the time.")
        for _ in range(100):
            if len(llm.requests) >= 2:
                break
            await asyncio.sleep(0.01)
        events = tool_events(engine)
        await engine.close()
        return handler, events, llm

    handler, events, llm = asyncio.run(scenario())
    handler.assert_not_called()
    assert ("declined", "user_declined") in events
    latest = llm.requests[-1]
    assert latest[-1] == {"role": "user", "content": "wait, keep it and tell me the time."}
    assert "was dropped" in latest[0]["content"]  # the model knows what was called off


def test_never_mind_during_a_confirmation_is_a_no():
    async def scenario():
        engine, handler, _ = await engine_with_pending_confirmation()
        engine.submit_text("Never mind.")
        await asyncio.wait_for(engine.reply, 2)
        events = tool_events(engine)
        await engine.close()
        return handler, events

    handler, events = asyncio.run(scenario())
    handler.assert_not_called()
    assert ("declined", "user_declined") in events


class SlowLLM:
    """Never finishes thinking, so the user can call it off."""

    def __init__(self) -> None:
        self.requests: list = []

    async def stream(self, messages, on_provider, tools=None):
        self.requests.append(messages)
        await asyncio.Event().wait()
        yield ""


def test_never_mind_while_thinking_cancels_without_asking_the_model_again():
    async def scenario():
        llm = SlowLLM()
        engine = CascadeEngine(FakeSTT(), FakeTTS(), llm)  # type: ignore[arg-type]
        await engine.start(SessionContext("s1"))
        engine.submit_text("Research solar batteries.")
        while not llm.requests:
            await asyncio.sleep(0.01)
        engine.submit_text("Never mind.")
        for _ in range(100):
            if "Okay, cancelled." in engine.tts.spoken:
                break
            await asyncio.sleep(0.01)
        done = engine.reply.done()
        await engine.close()
        return llm, engine.tts.spoken, done

    llm, spoken, done = asyncio.run(scenario())
    assert done and spoken == ["Okay, cancelled."]
    assert len(llm.requests) == 1


def test_a_new_request_while_thinking_replaces_the_old_one():
    async def scenario():
        llm = SlowLLM()
        engine = CascadeEngine(FakeSTT(), FakeTTS(), llm)  # type: ignore[arg-type]
        await engine.start(SessionContext("s1"))
        engine.submit_text("Weather in Paris.")
        while not llm.requests:
            await asyncio.sleep(0.01)
        engine.submit_text("Actually, weather in Rome.")
        while len(llm.requests) < 2:
            await asyncio.sleep(0.01)
        await engine.close()
        return llm

    llm = asyncio.run(scenario())
    assert llm.requests[1][-1]["content"] == "Actually, weather in Rome."
    assert "Weather in Paris." in llm.requests[1][0]["content"]  # told what was dropped


# Typed turns through the gateway


def test_a_typed_turn_is_shown_as_typed_and_limited_to_one_a_second(client, token):
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        assert json.loads(ws.receive_text()) == {"type": "state", "state": "idle"}
        ws.send_text(json.dumps({"type": "text.input", "text": "  What's   the weather? "}))
        echo = json.loads(ws.receive_text())
        assert echo["speaker"] == "user" and echo["typed"] is True and echo["final"] is True
        assert echo["text"] == "What's the weather?"
        ws.send_text(json.dumps({"type": "text.input", "text": "again"}))
        assert json.loads(ws.receive_text())["code"] == "rate_limited"


def test_typing_before_session_start_closes_the_session(client, token):
    with client.websocket_connect(f"/ws/session?token={token}", headers={"origin": ORIGIN}) as ws:
        ws.send_text(json.dumps({"type": "text.input", "text": "hello"}))
        assert json.loads(ws.receive_text()) == {"type": "session.end", "reason": "protocol_error"}



# Review fixes: hesitation, talking over the question, timeouts


@pytest.mark.parametrize("said", [
    "Okay, what is the weather tomorrow?", "Sure, tell me more about it", "Yeah, keep going",
    "Yes please, delete it.", "Yes but not that one",
])
def test_a_sentence_that_starts_with_yes_is_not_an_approval(said):
    # Security review: only an exact short yes approves by voice (T5).
    assert classify_confirmation(said)[0] is None


def test_the_summary_is_spoken_before_a_voice_answer():
    async def scenario():
        engine, _, _ = await engine_with_pending_confirmation()
        await asyncio.sleep(0.05)
        spoken = list(engine.tts.spoken)
        await engine.close()
        return spoken

    assert "Delete the test memory? Say yes or no." in asyncio.run(scenario())


def test_after_web_results_only_the_button_approves():
    async def scenario():
        engine, handler, _ = await engine_with_pending_confirmation()
        engine.bridge.tainted.add(engine.reply_message_id)
        engine.submit_text("Yes.")
        await asyncio.sleep(0.05)
        still_waiting = engine.bridge.pending_call() is not None
        engine.bridge.resolve(engine.bridge.pending_call(), True)  # the card's button
        await asyncio.wait_for(engine.reply, 2)
        await engine.close()
        return handler, still_waiting

    handler, still_waiting = asyncio.run(scenario())
    assert still_waiting
    handler.assert_awaited_once()


def test_hesitating_keeps_the_question_open():
    async def scenario():
        engine, handler, _ = await engine_with_pending_confirmation()
        engine.submit_text("Hmm.")
        engine.submit_text("Let me think.")
        assert engine.bridge.pending_call() is not None
        engine.submit_text("Yes.")
        await asyncio.wait_for(engine.reply, 2)
        await engine.close()
        return handler

    asyncio.run(scenario()).assert_awaited_once()


def test_saying_yes_over_the_question_answers_it_instead_of_cancelling():
    async def scenario():
        engine, handler, _ = await engine_with_pending_confirmation()
        # Barge-in while the question still plays: the gateway interrupts...
        await engine.interrupt(engine.reply_message_id, "")
        assert not engine.reply.cancelling()
        engine.submit_text("Yes.")  # ...and the final words answer it.
        await asyncio.wait_for(engine.reply, 2)
        await engine.close()
        return handler

    asyncio.run(scenario()).assert_awaited_once()


@pytest.mark.parametrize("sound", ["Umm.", "Okay."])
def test_a_filler_or_okay_while_thinking_does_not_cancel(sound):
    async def scenario():
        llm = SlowLLM()
        engine = CascadeEngine(FakeSTT(), FakeTTS(), llm)  # type: ignore[arg-type]
        await engine.start(SessionContext("s1"))
        engine.submit_text("Weather in Paris.")
        while not llm.requests:
            await asyncio.sleep(0.01)
        engine.submit_text(sound)
        await asyncio.sleep(0.05)
        alive = not engine.reply.done()
        await engine.close()
        return alive

    assert asyncio.run(scenario())


def test_never_mind_with_nothing_to_cancel_just_says_okay():
    async def scenario():
        tts = FakeTTS()
        engine = CascadeEngine(FakeSTT(), tts, ScriptedLLM())  # type: ignore[arg-type]
        await engine.start(SessionContext("s1"))
        engine.submit_text("Never mind.")
        await asyncio.wait_for(engine.reply, 2)
        await engine.close()
        return tts.spoken

    assert asyncio.run(scenario()) == ["Okay."]


def test_a_change_that_hangs_after_a_cancel_times_out_and_says_so():
    async def hang(args):
        await asyncio.Event().wait()

    bridge, _, emit = sensitive_bridge(hang, tool_timeout=0.05, filler_after=10)

    async def event(message):
        if isinstance(message, ToolConfirmRequest):
            bridge.resolve(message.call_id, True)

    emit.side_effect = event

    async def scenario():
        task = asyncio.create_task(bridge.execute(request(), "turn"))
        while not bridge.finishing:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert statuses(emit)[-1] == ("failed", None)
    assert not bridge.finishing
