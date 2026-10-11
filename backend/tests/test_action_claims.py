"""Action requests must use tools, and unsupported success claims never reach speech."""

import asyncio
import json

from app.cascade_engine import CascadeEngine
from app.llm import ToolCallRequest, ToolCalls
from app.skills import Skill

from .test_cascade import FakeSTT, FakeTTS


class RecordingBridge:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.done_after_cancel: list[str] = []
        self.executed: list[list[dict]] = []
        self.completed: dict[str, set[str]] = {}

    def model_tools(self) -> list[dict]:
        return [
            {"name": name, "description": name, "parameters": {"type": "object", "properties": {}}}
            for name in self.names
        ]

    async def execute(self, raw: str, turn_id: str, is_current=None) -> str:
        calls = json.loads(raw)
        self.executed.append(calls)
        self.completed.setdefault(turn_id, set()).update(call["name"] for call in calls)
        return '{"results": []}'

    def mutations_for(self, turn_id: str) -> frozenset[str]:
        return frozenset(self.completed.get(turn_id, ()))


class ReminderLLM:
    def __init__(self) -> None:
        self.requests: list[tuple[list[dict], list[dict] | None, object]] = []

    async def stream(self, messages, on_provider, tools=None, tool_choice=None):
        self.requests.append((messages, tools, tool_choice))
        if len(self.requests) == 1:
            yield "<toolcall>I'll set it."
            yield ToolCalls(
                [
                    ToolCallRequest("r1", "reminder_set", '{"text":"call mom","due_at":"2026-10-13T09:00"}'),
                    ToolCallRequest("r2", "reminder_set", '{"text":"duplicate","due_at":"2026-10-13T09:00"}'),
                    ToolCallRequest("x1", "task_add", '{"title":"unrelated"}'),
                ]
            )
        else:
            yield "The reminder is ready for confirmation."


def test_remind_me_offers_and_requires_the_reminder_tool():
    async def scenario():
        llm, tts = ReminderLLM(), FakeTTS()
        skill = Skill(
            id="remind-me",
            name="Remind me",
            triggers=["remind me"],
            allowed_tools=["reminder_set", "reminder_update", "memory_read"],
            instructions="Call reminder_set when the text and time are present.",
        )
        engine = CascadeEngine(FakeSTT(), tts, llm, skills=[skill])  # type: ignore[arg-type]
        bridge = RecordingBridge(["task_add", "reminder_set", "reminder_update", "memory_read"])
        engine.bridge = bridge  # type: ignore[assignment]
        await engine._answer("Remind me to call mom tomorrow at nine in the morning.", typed=True)
        return llm, bridge, tts

    llm, bridge, tts = asyncio.run(scenario())
    _, offered, choice = llm.requests[0]
    assert {tool["name"] for tool in offered} == {"reminder_set", "reminder_update", "memory_read"}
    assert choice == {"type": "function", "function": {"name": "reminder_set"}}
    assert [call["name"] for call in bridge.executed[0]] == ["reminder_set"]
    assert llm.requests[1][1] is None
    assert tts.spoken == ["The reminder is ready for confirmation."]


class FalseClaimLLM:
    def __init__(self) -> None:
        self.requests: list[list[dict]] = []

    async def stream(self, messages, on_provider, tools=None, tool_choice=None):
        self.requests.append([dict(message) for message in messages])
        yield "I've added the task."


def test_false_action_claim_is_retried_once_then_replaced_with_an_honest_reply():
    async def scenario():
        llm, tts = FalseClaimLLM(), FakeTTS()
        engine = CascadeEngine(FakeSTT(), tts, llm)  # type: ignore[arg-type]
        engine.bridge = RecordingBridge(["task_add"])  # type: ignore[assignment]
        await engine._answer("Add a task to buy milk tomorrow.", typed=True)
        return llm, tts

    llm, tts = asyncio.run(scenario())
    assert len(llm.requests) == 2
    retry = llm.requests[1][-1]
    assert retry["role"] == "system" and "task_add" in retry["content"]
    assert "I've added" not in retry["content"]
    assert tts.spoken == ["I couldn't complete that action."]


class PlainAnswerLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, messages, on_provider, tools=None, tool_choice=None):
        self.calls += 1
        yield "Full duplex means both sides can talk at once."


def test_plain_answer_does_not_trigger_the_action_safety_net():
    async def scenario():
        llm, tts = PlainAnswerLLM(), FakeTTS()
        engine = CascadeEngine(FakeSTT(), tts, llm)  # type: ignore[arg-type]
        engine.bridge = RecordingBridge(["task_add", "reminder_set"])  # type: ignore[assignment]
        await engine._answer("What does full duplex mean?", typed=True)
        return llm, tts

    llm, tts = asyncio.run(scenario())
    assert llm.calls == 1
    assert tts.spoken == ["Full duplex means both sides can talk at once."]


def test_declining_with_a_correction_carries_the_skill_and_tool_forward():
    class PendingBridge(RecordingBridge):
        cancel_reason = "interrupted"

        def pending_call(self):
            return "pending"

    skill = Skill(
        id="remind-me",
        name="Remind me",
        triggers=["remind me"],
        allowed_tools=["reminder_set"],
        instructions="Set the reminder.",
    )
    engine = CascadeEngine(FakeSTT(), FakeTTS(), PlainAnswerLLM(), skills=[skill])  # type: ignore[arg-type]
    engine.bridge = PendingBridge(["reminder_set"])  # type: ignore[assignment]
    engine.skill_active = skill
    engine.action_tool = "reminder_set"

    engine._on_final_input("No, make it ten.")

    assert engine.skill_next is skill
    assert engine.action_tool_next == "reminder_set"
    assert engine.user_turns.get_nowait() == ("make it ten.", False)
