"""End-to-end scenarios with real audio (plan P9).

Each one opens its own session, asks one warm-up question (not measured,
so cold starts do not count), then plays a user's part with the spoken
fixtures and records what happened. Times are on this machine's clock:
from the moment the last (or first) frame of the user's speech was sent.

- question: a spoken question; latency to the first audio of the answer.
- typed: the same for a typed question.
- barge_in: "Wait, stop." while TalkBack is answering; time until audio stops.
- backchannel: "Uh-huh." while TalkBack talks; it should keep talking.
- correction: "Remind me ... at nine", then "No wait, make it ten" while the
  confirmation is open; the 9:00 reminder must never be made.
- cancel_tool: "Never mind" while it looks up the weather; no answer follows.
"""

import asyncio
import time
from dataclasses import dataclass, field

import httpx

from audio_fixtures import pcm
from ws_client import LiveSession


@dataclass
class Result:
    scenario: str
    ok: bool
    ms: float | None = None  # the scenario's latency, if it has one
    note: str = ""
    outdated_action: bool = False  # a change the user had corrected happened anyway
    details: dict = field(default_factory=dict)


def _type(kind):
    return lambda m: m["type"] == kind


def _assistant_audio(m):
    return m["type"] == "audio.chunk"


async def _warm_up(s: LiveSession) -> None:
    since = s.mark()
    await s.type("Say OK.")
    await s.wait_for(lambda m: m["type"] == "state" and m["state"] == "idle", timeout=30, since=since + 1)
    await s.wait_for(_assistant_audio, timeout=5, since=since)
    while s.playing:
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)


async def _wait_quiet(s: LiveSession, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    await asyncio.sleep(0.5)
    while (s.playing or s.events and s.events[-1].msg.get("state") not in (None, "idle")) and time.monotonic() < deadline:
        await asyncio.sleep(0.1)


async def question(s: LiveSession) -> Result:
    since = s.mark()
    spoken = await s.say(pcm("capital_question"))
    audio = await s.wait_for(_assistant_audio, timeout=25, since=since)
    heard = s.first(lambda m: m["type"] == "transcript.delta" and m["speaker"] == "user" and m["final"], since)
    if audio is None:
        return Result("question", False, note="no answer within 25 s")
    return Result("question", True, (audio.t - spoken.ended) * 1000,
                  details={"heard": heard.msg["text"] if heard else None})


async def typed(s: LiveSession) -> Result:
    since = s.mark()
    sent = await s.type("What is the capital of Australia?")
    audio = await s.wait_for(_assistant_audio, timeout=25, since=since)
    if audio is None:
        return Result("typed", False, note="no answer within 25 s")
    return Result("typed", True, (audio.t - sent) * 1000)


async def _start_long_answer(s: LiveSession) -> bool:
    since = s.mark()
    await s.say(pcm("long_answer"))
    if await s.wait_for(_assistant_audio, timeout=25, since=since) is None:
        return False
    await asyncio.sleep(1.5)  # TalkBack has been talking for a moment
    return s.playing


async def barge_in(s: LiveSession) -> Result:
    if not await _start_long_answer(s):
        return Result("barge_in", False, note="the answer was too short to interrupt")
    since = s.mark()
    spoken = await s.say(pcm("wait_stop"))
    flush = await s.wait_for(lambda m: m["type"] == "audio.flush", timeout=4, since=since)
    trim = await s.wait_for(_type("transcript.trim"), timeout=2, since=since)
    if flush is None:
        return Result("barge_in", False, note="kept talking")
    return Result("barge_in", trim is not None, (flush.t - spoken.started) * 1000,
                  note="" if trim else "stopped, but no heard-words trim",
                  details={"heard_words": len(trim.msg["heard_text"].split()) if trim else None})


async def backchannel(s: LiveSession) -> Result:
    if not await _start_long_answer(s):
        return Result("backchannel", False, note="the answer was too short")
    since = s.mark()
    await s.say(pcm("uh_huh"))
    flush = await s.wait_for(lambda m: m["type"] == "audio.flush", timeout=2.5, since=since)
    return Result("backchannel", flush is None, note="stopped for a backchannel" if flush else "")


async def correction(s: LiveSession) -> Result:
    since = s.mark()
    await s.say(pcm("remind_nine"))
    ask = await s.wait_for(_type("tool.confirm_request"), timeout=25, since=since)
    if ask is None:
        return Result("correction", False, note="no confirmation was asked")
    first_call = ask.msg["call_id"]
    since = s.mark()
    await s.say(pcm("no_make_it_ten"))
    # The first request must end without running; a new one (ten) may follow.
    ended = await s.wait_for(lambda m: m["type"] == "tool.status" and m["call_id"] == first_call
                             and m["status"] != "running", timeout=15, since=since)
    again = await s.wait_for(lambda m: m["type"] == "tool.confirm_request" and m["call_id"] != first_call,
                             timeout=20, since=since)
    if again is not None:
        await s.confirm(again.msg["call_id"], True)
        await s.wait_for(lambda m: m["type"] == "tool.status" and m["call_id"] == again.msg["call_id"]
                         and m["status"] != "running", timeout=10, since=since)
    reminders = await _reminders(s)
    nine = [r for r in reminders if "T09:00" in r["due_at"]]
    ten = [r for r in reminders if "T10:00" in r["due_at"]]
    await _cleanup(s, reminders)
    first_status = ended.msg["status"] if ended else "none"
    return Result(
        "correction", not nine and first_status != "done" and bool(ten), outdated_action=bool(nine),
        note="" if ten else "the corrected reminder was not set",
        details={"first_request": first_status, "corrected_request": again is not None},
    )


async def cancel_tool(s: LiveSession) -> Result:
    since = s.mark()
    await s.say(pcm("weather_tokyo"))
    busy = await s.wait_for(lambda m: m["type"] == "state" and m["state"] in ("thinking", "tool"), timeout=15, since=since)
    if busy is None:
        return Result("cancel_tool", False, note="never started thinking")
    await asyncio.sleep(0.3)
    since = s.mark()
    await s.say(pcm("never_mind"))
    await _wait_quiet(s, 15)
    said = " ".join(e.msg["text"] for e in s.events[since:]
                    if e.msg["type"] == "transcript.delta" and e.msg["speaker"] == "assistant")
    weather = any(word in said.lower() for word in ("degrees", "°", "tokyo", "sunny", "rain", "cloud"))
    return Result("cancel_tool", not weather, note="answered anyway" if weather else "", details={"said": said[:120]})


async def _reminders(s: LiveSession) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(f"{s.base}/api/reminders", headers={"Authorization": f"Bearer {s.token}"})
        return r.json()["items"] if r.status_code == 200 else []


async def _cleanup(s: LiveSession, reminders: list[dict]) -> None:
    async with httpx.AsyncClient(timeout=20) as http:
        for r in reminders:
            await http.delete(f"{s.base}/api/reminders/{r['id']}", headers={"Authorization": f"Bearer {s.token}"})


SCENARIOS = {
    "question": question, "typed": typed, "barge_in": barge_in, "backchannel": backchannel,
    "correction": correction, "cancel_tool": cancel_tool,
}


async def run(name: str, base: str, code: str = "") -> Result:
    try:
        async with LiveSession(base, code) as s:
            await _warm_up(s)
            return await asyncio.wait_for(SCENARIOS[name](s), timeout=90)
    except Exception as exc:  # a run that breaks counts as failed, with why
        return Result(name, False, note=f"{type(exc).__name__}")
