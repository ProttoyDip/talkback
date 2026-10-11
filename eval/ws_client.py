"""A client that behaves like the browser, for end-to-end runs (plan P9).

It gets a session token, opens the WebSocket with the page's Origin, and
then, like the page:

- sends a 20 ms microphone frame every 20 ms, all the time (silence between
  utterances, real speech when a scenario speaks);
- "plays" the assistant's audio at 22.05 kHz as it arrives, and reports
  playback.position every 100 ms and right after a flush, so the server can
  tell which words were heard.

Not simulated: echo of TalkBack's own voice into the microphone (the page
relies on the browser's echo cancellation), and network jitter beyond the
real network's.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx
import websockets

FRAME_BYTES = 640  # 20 ms at 16 kHz, 16-bit mono
FRAME_S = 0.02
OUT_RATE = 22_050


@dataclass
class Event:
    t: float  # time.monotonic() when it arrived
    msg: dict


@dataclass
class Spoken:
    started: float  # first frame of the utterance sent
    ended: float  # last frame sent


@dataclass
class LiveSession:
    base: str
    access_code: str = ""
    events: list[Event] = field(default_factory=list)
    received: int = 0  # assistant samples received
    played: float = 0.0  # ...and "played"
    chunks: list[tuple[int, int]] = field(default_factory=list)  # (seq, cumulative end sample)
    flushed: bool = False

    async def __aenter__(self) -> "LiveSession":
        headers = {"X-Access-Code": self.access_code} if self.access_code else {}
        async with httpx.AsyncClient(timeout=90) as http:  # a sleeping free server takes a while
            auth = (await http.get(f"{self.base}/api/auth-config")).json()
            if auth.get("mode", "off") != "off":
                # Accounts are on: sign in as a guest (Supabase anonymous sign-in), like "Continue as guest".
                guest = await http.post(f"{auth['supabase_url']}/auth/v1/signup",
                                        headers={"apikey": auth["publishable_key"]}, json={})
                guest.raise_for_status()
                headers["Authorization"] = f"Bearer {guest.json()['access_token']}"
            response = await http.post(f"{self.base}/api/session", headers=headers)
            response.raise_for_status()
            self.token = response.json()["token"]
        scheme = "wss" if self.base.startswith("https") else "ws"
        host = self.base.split("://", 1)[1].rstrip("/")
        self.ws = await websockets.connect(
            f"{scheme}://{host}/ws/session?token={self.token}", origin=self.base, max_size=None,
        )
        self._mic: bytearray = bytearray()
        self._mic_waiters: list[tuple[int, asyncio.Future]] = []
        self._sent_bytes = 0
        self._tasks = [asyncio.create_task(f()) for f in (self._read, self._mic_loop, self._playback_loop)]
        await self.ws.send(json.dumps({"type": "session.start", "client_sample_rate": 16000}))
        await self.wait_for(lambda m: m["type"] == "state" and m["state"] == "idle", timeout=30)
        return self

    async def __aexit__(self, *exc) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.ws.close()

    # Receiving

    async def _read(self) -> None:
        async for message in self.ws:
            now = time.monotonic()
            if isinstance(message, bytes):
                self.received += len(message) // 2
                if self.chunks:
                    seq, _ = self.chunks[-1]
                    self.chunks[-1] = (seq, self.received)
                continue
            msg = json.loads(message)
            if msg["type"] == "audio.chunk":
                self.chunks.append((msg["seq"], self.received + msg["samples"]))
            elif msg["type"] == "audio.flush":
                self.received = int(self.played)  # whatever was queued is dropped
                self.flushed = True
            self.events.append(Event(now, msg))

    def mark(self) -> int:
        """An index into events: wait_for looks only at what comes after it."""
        return len(self.events)

    async def wait_for(self, match, timeout: float = 20, since: int = 0) -> Event | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events[since:]:
                if match(event.msg):
                    return event
            await asyncio.sleep(0.01)
        return None

    def first(self, match, since: int = 0) -> Event | None:
        return next((e for e in self.events[since:] if match(e.msg)), None)

    # Playback

    @property
    def playing(self) -> bool:
        return self.played < self.received

    async def _playback_loop(self) -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.1)
            now = time.monotonic()
            self.played = min(float(self.received), self.played + (now - last) * OUT_RATE)
            last = now
            if self.chunks and (self.playing or self.flushed):
                self.flushed = False
                seq = next((s for s, end in self.chunks if end > self.played), self.chunks[-1][0])
                await self.ws.send(json.dumps({"type": "playback.position", "seq": seq, "samples_played": int(self.played)}))

    # Speaking

    async def _mic_loop(self) -> None:
        start = time.monotonic()
        frames = 0
        while True:
            frames += 1
            await asyncio.sleep(max(0.0, start + frames * FRAME_S - time.monotonic()))
            if len(self._mic) >= FRAME_BYTES:
                frame = bytes(self._mic[:FRAME_BYTES])
                del self._mic[:FRAME_BYTES]
            else:
                frame = bytes(self._mic) + b"\x00" * (FRAME_BYTES - len(self._mic))
                self._mic.clear()
            await self.ws.send(frame)
            self._sent_bytes += FRAME_BYTES
            for target, future in list(self._mic_waiters):
                if self._sent_bytes >= target and not future.done():
                    future.set_result(time.monotonic())
                    self._mic_waiters.remove((target, future))

    async def say(self, pcm: bytes) -> Spoken:
        """Speak into the mic in real time; returns when the last frame went out."""
        loop = asyncio.get_running_loop()
        started = loop.create_future()
        ended = loop.create_future()
        queued = self._sent_bytes + len(self._mic)
        self._mic_waiters.append((queued + FRAME_BYTES, started))
        self._mic.extend(pcm)
        self._mic_waiters.append((queued + len(pcm), ended))
        return Spoken(await started, await ended)

    async def type(self, text: str) -> float:
        await self.ws.send(json.dumps({"type": "text.input", "text": text}))
        return time.monotonic()

    async def confirm(self, call_id: str, approved: bool) -> None:
        await self.ws.send(json.dumps({"type": "tool.confirm", "call_id": call_id, "approved": approved}))
