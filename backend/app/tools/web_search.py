"""Web search: Tavily first, Perplexity second (plan.md X11).

Both return source excerpts only. The bridge sanitizes and wraps the results
as untrusted data (SECURITY.md T1).
"""
import logging

import httpx
from pydantic import Field, SecretStr

from . import Arguments, Tool, ToolResult

log = logging.getLogger("talkback.search")


class SearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=3, ge=1, le=5)


async def _tavily(client: httpx.AsyncClient, key: SecretStr, arguments: SearchArguments) -> list[ToolResult]:
    response = await client.post("https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        json={"query": arguments.query, "max_results": arguments.max_results,
              "include_answer": False, "include_raw_content": False},
        timeout=4, follow_redirects=False)
    response.raise_for_status()
    return [ToolResult(str(item["title"]), str(item["url"]), str(item["content"]))
            for item in response.json()["results"][:arguments.max_results]]


async def _perplexity(client: httpx.AsyncClient, key: SecretStr, arguments: SearchArguments) -> list[ToolResult]:
    response = await client.post("https://api.perplexity.ai/search",
        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
        json={"query": arguments.query, "max_results": arguments.max_results},
        timeout=4, follow_redirects=False)
    response.raise_for_status()
    return [ToolResult(str(item["title"]), str(item["url"]), str(item.get("snippet", "")))
            for item in response.json()["results"][:arguments.max_results]]


def web_search_tool(client: httpx.AsyncClient, tavily_key: SecretStr,
                    perplexity_key: SecretStr | None = None) -> Tool:
    async def run(arguments: SearchArguments) -> list[ToolResult]:
        providers = [(name, search, key) for name, search, key in
                     (("tavily", _tavily, tavily_key), ("perplexity", _perplexity, perplexity_key))
                     if key is not None and key.get_secret_value()]
        if not providers:
            raise ValueError("search is not configured")
        for index, (name, search, key) in enumerate(providers):
            try:
                return await search(client, key, arguments)
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                log.warning("search provider failed", extra={"event": name})
                if index == len(providers) - 1:
                    raise
        raise ValueError("search is not configured")
    return Tool("web_search", "Search the web.", SearchArguments, run, sensitive=False)
