"""X5 and the settings routes."""

import asyncio

import pytest
from pydantic import SecretStr

from app.llm import ToolCallRequest, ToolCalls
from app.skills import Skill, load_skills, match_trigger

from .test_cascade import FakeSTT, FakeTTS


@pytest.fixture
def authed(client, settings, tmp_path):
    settings.settings_path = str(tmp_path / "settings.json")
    settings.skills_dir = "skills"
    settings.nebius_api_key = SecretStr("n")
    token = client.post("/api/session").json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_settings_need_a_token(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/skills").status_code == 401


def test_settings_default_to_private_choices(client, authed):
    view = client.get("/api/settings", headers=authed).json()
    assert view["save_recordings"] is False and view["transcripts_in_logs"] is False
    assert view["tools"]["weather"]["enabled"] is True
    assert view["models"]["providers"][0]["id"] == "nebius"


def test_settings_changes_are_saved(client, authed):
    view = client.patch(
        "/api/settings", headers=authed, json={"tools": {"weather": False}, "save_recordings": True}
    ).json()
    assert view["tools"]["weather"]["enabled"] is False and view["save_recordings"] is True
    assert client.get("/api/settings", headers=authed).json()["tools"]["weather"]["enabled"] is False


def test_unknown_or_unavailable_planner_model_is_refused(client, authed):
    assert client.patch("/api/settings", headers=authed, json={"planner_model": "evil:model"}).status_code == 422
    options = client.get("/api/settings", headers=authed).json()["models"]["planner_options"]
    offline = next(o for o in options if not o["available"])  # OpenRouter has no key here
    assert client.patch("/api/settings", headers=authed, json={"planner_model": offline["id"]}).status_code == 422


def test_unknown_fields_are_rejected(client, authed):
    assert client.patch("/api/settings", headers=authed, json={"nonsense": 1}).status_code == 422


def test_skills_listed_and_run_needs_a_live_session(client, authed):
    items = client.get("/api/skills", headers=authed).json()["items"]
    assert {s["id"] for s in items} >= {"morning-brief", "quick-research", "remind-me"}
    assert client.post("/api/skills/nope/run", headers=authed).status_code == 404
    assert client.post("/api/skills/morning-brief/run", headers=authed).status_code == 409


def test_shipped_skills_load_and_trigger_by_voice():
    skills = load_skills("skills")
    assert match_trigger("Give me my morning brief please", skills).id == "morning-brief"
    assert match_trigger("what time is it", skills) is None


def test_a_skill_cannot_call_a_tool_outside_its_list():
    from app.cascade_engine import CascadeEngine

    class Bridge:
        executed: list = []

        def model_tools(self):
            return [{"name": "weather"}, {"name": "web_search"}]

        async def execute(self, raw, turn_id):
            self.executed.append(raw)
            return "RESULT"

    skill = Skill(id="s", name="S", triggers=["s"], allowed_tools=["weather"], instructions="x")
    engine = CascadeEngine(FakeSTT(), FakeTTS(), llm=None)  # type: ignore[arg-type]
    engine.bridge = Bridge()  # type: ignore[assignment]
    engine.skill_active = skill
    messages: list = []
    calls = ToolCalls(
        [ToolCallRequest("1", "weather", '{"location": "Paris"}'), ToolCallRequest("2", "web_search", '{"query": "x"}')]
    )
    asyncio.run(engine._run_tools(calls, "m", messages))
    sent = Bridge.executed[0]
    assert "weather" in sent and "web_search" not in sent  # the bridge never saw the blocked call
    contents = {m["tool_call_id"]: m["content"] for m in messages if m["role"] == "tool"}
    assert contents["1"] == "RESULT" and "not_allowed" in contents["2"]


def test_conversation_settings_are_saved_and_validated(client, authed):
    view = client.get("/api/settings", headers=authed).json()
    assert view["interrupt_sensitivity"] == "normal" and view["answer_length"] == "normal"
    view = client.patch(
        "/api/settings", headers=authed, json={"interrupt_sensitivity": "low", "answer_length": "short"}
    ).json()
    assert view["interrupt_sensitivity"] == "low" and view["answer_length"] == "short"
    assert client.patch("/api/settings", headers=authed, json={"answer_length": "huge"}).status_code == 422


def test_sensitivity_changes_the_interrupt_thresholds():
    from app.turn_taking import BargeInDecider

    low, high = BargeInDecider.for_sensitivity("low"), BargeInDecider.for_sensitivity("high")
    assert low.update(300, "wait") == "none"  # a noisy room needs longer speech
    assert high.update(200, "wait") == "interrupt"
    assert BargeInDecider.for_sensitivity("nonsense").min_speech_ms == 250


def test_answer_length_reaches_the_prompt():
    from app.cascade_engine import ANSWER_LENGTH

    assert "one short sentence" in ANSWER_LENGTH["short"] and ANSWER_LENGTH["normal"] == ""
