"""Tavily REST search, returning source excerpts only."""
import httpx
from pydantic import Field, SecretStr
from . import Arguments, Tool, ToolResult

class SearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=3, ge=1, le=5)


def web_search_tool(client: httpx.AsyncClient, api_key: SecretStr) -> Tool:
    async def run(arguments: SearchArguments) -> list[ToolResult]:
        if not api_key.get_secret_value():
            raise ValueError("search is not configured")
        response = await client.post("https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            json={"query": arguments.query, "max_results": arguments.max_results,
                  "include_answer": False, "include_raw_content": False},
            timeout=4, follow_redirects=False)
        response.raise_for_status()
        return [ToolResult(str(item["title"]), str(item["url"]), str(item["content"]))
                for item in response.json()["results"][:arguments.max_results]]
    return Tool("web_search", "Send the requested search query to Tavily?", SearchArguments, run)
