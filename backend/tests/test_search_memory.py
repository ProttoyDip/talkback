"""X11 search fallback and memory saved from the user's own words."""

import asyncio

import httpx
from pydantic import SecretStr

from app.cascade_engine import CascadeEngine
from app.memory import MemoryStore
from app.tools.web_search import SearchArguments, web_search_tool
from app.voice_engine import ProtocolEvent

from .test_cascade import FakeSTT, FakeTTS


def search(handler, tavily="t", perplexity="p"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tool = web_search_tool(client, SecretStr(tavily), SecretStr(perplexity))
            return await tool.run(SearchArguments(query="duplex"))

    return asyncio.run(run())


def test_search_uses_tavily_first():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json={"results": [{"title": "T", "url": "https://a.test", "content": "c"}]})

    assert search(handler)[0].title == "T"
    assert hosts == ["api.tavily.com"]


def test_tavily_failure_switches_to_perplexity():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "api.tavily.com":
            return httpx.Response(429)
        return httpx.Response(200, json={"results": [{"title": "P", "url": "https://b.test", "snippet": "s"}]})

    result = search(handler)
    assert result[0].title == "P" and result[0].snippet == "s"
    assert hosts == ["api.tavily.com", "api.perplexity.ai"]


def test_search_without_any_key_is_not_configured():
    try:
        search(lambda r: httpx.Response(200), tavily="", perplexity="")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_remember_request_saves_a_memory_from_the_users_words(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    engine = CascadeEngine(FakeSTT(), FakeTTS(), llm=None, memory_store=store)  # type: ignore[arg-type]

    async def run():
        return await engine._save_memory("Remember that I prefer Celsius.")

    assert asyncio.run(run()) == "I prefer Celsius"
    item = store.list()[0]
    assert item.text == "I prefer Celsius" and item.utterance == "Remember that I prefer Celsius."
    saved = [e for e in list(engine.queue._queue) if isinstance(e, ProtocolEvent)]
    assert saved and saved[0].message.type == "memory.saved"


def test_ordinary_requests_save_nothing(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    engine = CascadeEngine(FakeSTT(), FakeTTS(), llm=None, memory_store=store)  # type: ignore[arg-type]
    assert asyncio.run(engine._save_memory("What is the weather?")) is None
    assert store.list() == []
