"""NVIDIA hosted speech on the API catalog (build.nvidia.com), via Riva gRPC.

- Speech-to-text: Parakeet, streaming, 16 kHz PCM16.
- Text-to-speech: Magpie TTS, 22.05 kHz PCM16, with word timing when the
  model provides it.

The Riva client is blocking, so it runs on worker threads. The API key goes
only into gRPC metadata; it is never logged.
"""

import asyncio
import logging
import queue
import threading
from collections.abc import Callable, Iterator

import grpc
import riva.client
from pydantic import SecretStr

from . import SAMPLE_RATE_OUT, Speech, estimate_word_times

log = logging.getLogger("talkback.speech")

# NVCF streams end after a while; reopen them, but give up after repeated failures.
MAX_STREAM_RESTARTS = 5


def _auth(server: str, function_id: str, api_key: SecretStr) -> riva.client.Auth:
    return riva.client.Auth(
        uri=server,
        use_ssl=True,
        metadata_args=[["function-id", function_id], ["authorization", f"Bearer {api_key.get_secret_value()}"]],
    )


class RivaStreamingASR:
    def __init__(self, server: str, function_id: str, api_key: SecretStr, stop_history_ms: int = 500) -> None:
        self.server = server
        self.stop_history_ms = stop_history_ms
        self.function_id = function_id
        self.api_key = api_key
        self.frames: queue.Queue[bytes | None] = queue.Queue(maxsize=500)  # 10 s of audio
        self.closed = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self, on_result: Callable[[str, bool], None], on_error: Callable[[str], None]) -> None:
        self.thread = threading.Thread(target=self._run, args=(on_result, on_error), daemon=True, name="riva-asr")
        self.thread.start()

    def push(self, frame: bytes) -> None:
        try:
            self.frames.put_nowait(frame)
        except queue.Full:
            pass  # the recognizer is behind; dropping beats unbounded memory

    def close(self) -> None:
        self.closed.set()
        try:
            self.frames.put_nowait(None)
        except queue.Full:
            pass

    def _audio(self) -> Iterator[bytes]:
        while not self.closed.is_set():
            frame = self.frames.get()
            if frame is None:
                return
            yield frame

    def _run(self, on_result: Callable[[str, bool], None], on_error: Callable[[str], None]) -> None:
        config = riva.client.StreamingRecognitionConfig(
            config=riva.client.RecognitionConfig(
                encoding=riva.client.AudioEncoding.LINEAR_PCM,
                sample_rate_hertz=16_000,
                language_code="en-US",
                max_alternatives=1,
                enable_automatic_punctuation=True,
                audio_channel_count=1,
            ),
            interim_results=True,
        )
        # End of turn after this much silence (the service default waits longer).
        riva.client.add_endpoint_parameters_to_config(
            config,
            start_history=-1,
            start_threshold=-1,
            stop_history=self.stop_history_ms,
            stop_history_eou=max(1, self.stop_history_ms // 2),
            stop_threshold=-1,
            stop_threshold_eou=-1,
        )
        failures = 0
        while not self.closed.is_set():
            try:
                service = riva.client.ASRService(_auth(self.server, self.function_id, self.api_key))
                for response in service.streaming_response_generator(self._audio(), config):
                    failures = 0
                    for result in response.results:
                        if result.alternatives:
                            on_result(result.alternatives[0].transcript, result.is_final)
            except grpc.RpcError as error:
                if self.closed.is_set():
                    return
                failures += 1
                log.warning("speech-to-text stream failed", extra={"code": str(error.code())})
                if error.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
                    on_error("Speech recognition rejected the NVIDIA API key. Check NVIDIA_API_KEY.")
                    return
                if failures >= MAX_STREAM_RESTARTS:
                    on_error("Speech recognition isn't reachable right now. Please try again.")
                    return


class RivaTTS:
    def __init__(self, server: str, function_id: str, api_key: SecretStr, voice: str) -> None:
        self.server = server
        self.function_id = function_id
        self.api_key = api_key
        self.voice = voice
        self.word_timing = True  # turned off if the model rejects the option
        self._service: riva.client.SpeechSynthesisService | None = None

    def _synthesize(self, text: str) -> Speech:
        if self._service is None:
            self._service = riva.client.SpeechSynthesisService(_auth(self.server, self.function_id, self.api_key))
        kwargs = dict(
            voice_name=self.voice,
            language_code="en-US",
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            sample_rate_hz=SAMPLE_RATE_OUT,
        )
        try:
            response = self._service.synthesize(text, enable_word_time_offsets=self.word_timing or None, **kwargs)
        except grpc.RpcError as error:
            if self.word_timing and error.code() in (grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.UNIMPLEMENTED):
                self.word_timing = False
                response = self._service.synthesize(text, **kwargs)
            else:
                raise
        speech = Speech(pcm=bytes(response.audio))
        words = [(w.word, float(w.start_time), float(w.end_time)) for w in response.meta.words]
        if words:
            # Riva reports milliseconds; convert when the numbers are clearly ms.
            if max(end for _, _, end in words) > speech.duration_s * 5:
                words = [(w, s / 1000, e / 1000) for w, s, e in words]
            return Speech(pcm=speech.pcm, words=words)
        return Speech(pcm=speech.pcm, words=estimate_word_times(text, speech.duration_s))

    async def synthesize(self, text: str) -> Speech:
        return await asyncio.to_thread(self._synthesize, text)
