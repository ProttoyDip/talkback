"""Reduce external results to bounded plain text, never executable input."""

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .tools import ToolResult


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = "".join((attributes.get("style") or "").lower().split())
        hidden = (
            tag in {"script", "style", "template", "noscript", "head", "iframe", "svg"}
            or "hidden" in attributes
            or attributes.get("aria-hidden", "").lower() == "true"
            or any(value in style for value in ("display:none", "visibility:hidden", "opacity:0"))
            or bool(attributes.get("class"))  # CSS visibility cannot be resolved without a browser.
            or any(item[1] for item in self.stack)
        )
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, hidden))
        self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not any(item[1] for item in self.stack):
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value[:100_000])
    parser.close()
    return " ".join("".join(parser.parts).split())


def sanitize(result: ToolResult) -> dict[str, str]:
    title = plain_text(result.title)[:300]
    url = result.url.strip()
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            url = ""
    except ValueError:
        url = ""
    url = url[:700]
    return {"title": title, "url": url, "snippet": plain_text(result.snippet)[:2000 - len(title) - len(url)]}


def wrap_results(results: list[dict]) -> str:
    # Escape delimiters even inside strings, so content cannot close the data block.
    payload = json.dumps(results, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"<TOOL_RESPONSE>{payload}</TOOL_RESPONSE>"
