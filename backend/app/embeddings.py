"""Text embeddings from the NVIDIA API catalog (plan P8).

Documents are embedded as "passage" and searches as "query". Failure is
not fatal: passages are stored without an embedding and found by keywords,
so an upload never fails because NVIDIA is busy.
"""

import logging

import httpx
from pydantic import SecretStr

log = logging.getLogger("talkback.embeddings")

URL = "https://integrate.api.nvidia.com/v1/embeddings"
BATCH = 32


class Embedder:
    def __init__(self, key: SecretStr, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.key = key
        self.model = model
        self.client = client

    @property
    def available(self) -> bool:
        return bool(self.key.get_secret_value())

    async def embed(self, texts: list[str], input_type: str, timeout: float = 30) -> list[list[float]] | None:
        """One vector per text, or None if NVIDIA could not be reached."""
        if not self.available or not texts:
            return None
        client = self.client or httpx.AsyncClient(follow_redirects=False)
        try:
            vectors: list[list[float]] = []
            for start in range(0, len(texts), BATCH):
                response = await client.post(URL, timeout=timeout, headers={
                    "Authorization": f"Bearer {self.key.get_secret_value()}",
                }, json={
                    "model": self.model, "input": texts[start:start + BATCH], "input_type": input_type,
                    "encoding_format": "float", "truncate": "END",
                })
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors.extend([float(x) for x in item["embedding"]] for item in data)
            return vectors if len(vectors) == len(texts) else None
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            # The exception type and status only: never the text or the response.
            status = f" {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else ""
            log.warning("embedding failed", extra={"event": type(exc).__name__ + status})
            return None
        finally:
            if self.client is None:
                await client.aclose()


def embedder_for(settings, client: httpx.AsyncClient | None = None) -> Embedder:
    return Embedder(settings.nvidia_api_key, settings.embed_model, client)
