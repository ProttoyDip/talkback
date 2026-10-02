"""Nemotron chat client for spoken replies (plan.md X12; X10 extends this).

OpenAI-compatible streaming over httpx. Providers are tried in order:
Nebius Token Factory first (hackathon rule), OpenRouter as the backup.
A provider is skipped when it has no key, and a failure before the first
token moves on to the next one. Keys never appear in logs or errors.
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

import httpx
from pydantic import SecretStr

from .config import Settings
from .protocol import ProviderId

log = logging.getLogger("talkback.llm")

NEMOTRON_NANO = "nvidia/nvidia-nemotron-3-nano-30b-a3b"  # Nebius Token Factory ID
NEMOTRON_NANO_OPENROUTER = "nvidia/nemotron-3-nano-30b-a3b"

# Status codes that mean "try the next provider" (plan.md 8.2).
SWITCH_STATUSES = {401, 402, 403, 408, 429} | set(range(500, 600))


@dataclass(frozen=True)
class LlmProvider:
    id: ProviderId
    base_url: str
    model: str
    api_key: SecretStr
    primary: bool
    # Thinking is turned off: it delays the first spoken word by ~10 s.
    extra_body: dict = field(default_factory=dict)


def providers_from_settings(settings: Settings) -> list[LlmProvider]:
    candidates = [
        LlmProvider(
            id="nebius",
            base_url="https://api.tokenfactory.nebius.com/v1",
            model=settings.nebius_llm_model,
            api_key=settings.nebius_api_key,
            primary=True,
            # Assumption until checked with a key: vLLM-style template switch.
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        ),
        LlmProvider(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model=settings.openrouter_llm_model,
            api_key=settings.openrouter_api_key,
            primary=False,
            extra_body={"reasoning": {"enabled": False}},
        ),
    ]
    return [p for p in candidates if p.api_key.get_secret_value()]


class LlmUnavailable(Exception):
    """No provider could answer. The message is safe to show."""


class LlmClient:
    def __init__(self, providers: list[LlmProvider], client: httpx.AsyncClient, timeout: float = 10.0) -> None:
        self.providers = providers
        self.client = client
        self.timeout = timeout

    async def stream(
        self,
        messages: list[dict[str, str]],
        on_provider: Callable[[LlmProvider], None],
        max_tokens: int = 300,
    ) -> AsyncIterator[str]:
        """Yield reply text as it arrives. on_provider is called once, with the
        provider that answers, before the first piece of text."""
        if not self.providers:
            raise LlmUnavailable("No language model is configured. Add NEBIUS_API_KEY or OPENROUTER_API_KEY.")
        for provider in self.providers:
            body = {
                "model": provider.model,
                "messages": messages,
                "stream": True,
                "max_tokens": max_tokens,
                **provider.extra_body,
            }
            headers = {"Authorization": f"Bearer {provider.api_key.get_secret_value()}"}
            started = False
            try:
                async with self.client.stream(
                    "POST", f"{provider.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout
                ) as response:
                    if response.status_code in SWITCH_STATUSES:
                        log.warning("llm provider failed", extra={"event": provider.id, "code": response.status_code})
                        continue
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        try:
                            choice = json.loads(line[6:])["choices"][0]
                        except (ValueError, KeyError, IndexError):
                            continue
                        text = (choice.get("delta") or {}).get("content") or ""
                        if text:
                            if not started:
                                started = True
                                on_provider(provider)
                            yield text
                    if started:
                        return
                    log.warning("llm provider returned no text", extra={"event": provider.id})
            except httpx.HTTPError:
                if started:
                    raise  # mid-reply failures are not retried: words were already spoken
                log.warning("llm provider unreachable", extra={"event": provider.id})
        raise LlmUnavailable("The language model isn't reachable right now. Please try again.")
