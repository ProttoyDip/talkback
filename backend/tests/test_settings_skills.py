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
