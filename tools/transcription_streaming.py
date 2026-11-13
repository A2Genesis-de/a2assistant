"""Live speech-to-text: feed microphone PCM while the user speaks, get partial and final text.

Every caller hands 16 kHz mono s16le PCM to :meth:`StreamingSession.push_audio` in any chunk
size, receives non-final text through ``on_partial`` as the provider recognizes it, and calls
:meth:`StreamingSession.finalize` at end of speech for the standard transcription envelope
(``success`` / ``transcript`` / ``provider`` / ``error``). One worker thread owns the provider
socket, so callers never block on network I/O while audio is captured.

Built-in wire: ``openai``, a Realtime ``type: transcription`` session (``stt.openai.streaming_model``,
default ``gpt-live-transcribe``, the one model that emits deltas before the turn is committed). The
endpoint requires >= 24 kHz input, so PCM is resampled 16 k -> 24 k here.

Plugin providers opt in through ``TranscriptionProvider.streaming_capable`` /
``open_stream_session``. Streaming is opt-in (``stt.streaming: true``); every surface falls back
to the file path when no session opens or a session fails.
"""

from __future__ import annotations

import base64
import contextvars
import json
import logging
import queue
import threading
import time
from array import array
from typing import Any, Callable, Optional
from urllib.parse import urlsplit, urlunsplit

from agent.memory_provider import spawn_context_thread
from utils import is_truthy_value

logger = logging.getLogger(__name__)

INPUT_RATE = 16000  # the contract every caller feeds
DEFAULT_OPENAI_STREAMING_MODEL = "gpt-live-transcribe"
STREAMING_PROVIDERS = ("openai",)
_FINALIZE_TIMEOUT_S = 20.0
_CONNECT_TIMEOUT_S = 10.0

PartialCallback = Callable[[str], None]


class Resampler:
    """Stateful s16le mono rate converter (linear; box-average for integer downsampling)."""

    def __init__(self, src_rate: int, dst_rate: int) -> None:
        self.src, self.dst = int(src_rate), int(dst_rate)
        self._pos = 0.0  # fractional read position into the carried + new samples
        self._carry = array("h")

    def __call__(self, pcm: bytes) -> bytes:
        if self.src == self.dst or not pcm:
            return pcm
        samples = array("h")
        samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        if self.src % self.dst == 0:
            data = self._carry + samples
            step = self.src // self.dst
            usable = len(data) - len(data) % step
            out = array("h", (sum(data[i:i + step]) // step for i in range(0, usable, step)))
            self._carry = data[usable:]
            return out.tobytes()
        data = self._carry + samples
        ratio = self.src / self.dst
        out = array("h")
        pos = self._pos
        last = len(data) - 1
        while pos < last:
            i = int(pos)
            frac = pos - i
            out.append(int(data[i] + (data[i + 1] - data[i]) * frac))
            pos += ratio
        keep = int(pos)
        self._carry = data[keep:]
        self._pos = pos - keep
        return out.tobytes()


class StreamingSession:
    """One utterance of live STT. Thread-safe ``push_audio``; single-use."""

    provider = "unknown"

    def __init__(self, on_partial: Optional[PartialCallback] = None) -> None:
        self._on_partial = on_partial
        self._audio: queue.Queue[Optional[bytes]] = queue.Queue()
        self._done = threading.Event()
        self._cancelled = threading.Event()
        self._result: dict[str, Any] = {}
        self._partial = ""
        self._worker: Optional[threading.Thread] = None
        self._to_16k: Optional[Resampler] = None

    def set_input_rate(self, rate: int) -> None:
        """Accept PCM at ``rate`` (e.g. the mic's device rate); the worker converts it to 16 kHz,
        so a realtime capture callback never pays for resampling."""
        if int(rate) != INPUT_RATE:
            self._to_16k = Resampler(int(rate), INPUT_RATE)

    def _take_audio(self, block: bool, timeout: float = 0.0) -> Optional[bytes]:
        """Next 16 kHz chunk (``b""`` when none is queued, None at end of audio)."""
        try:
            chunk = self._audio.get(timeout=timeout) if block else self._audio.get_nowait()
        except queue.Empty:
            return b""
        if chunk and self._to_16k is not None:
            chunk = self._to_16k(chunk)
        return chunk

    # ── caller API ──
    def start(self) -> StreamingSession:
        # copy_context: a plugin session reads secrets from the opener's profile scope.
        ctx = contextvars.copy_context()
        self._worker = threading.Thread(target=ctx.run, args=(self._run,), name=f"stt-stream-{self.provider}",
                                        daemon=True)
        self._worker.start()
        return self

    def push_audio(self, pcm16k: bytes) -> None:
        if pcm16k and not self._done.is_set():
            self._audio.put(bytes(pcm16k))

    def end_audio(self) -> None:
        """Signal end of speech without waiting (the worker flushes the provider)."""
        self._audio.put(None)

    def finalize(self, timeout: float = _FINALIZE_TIMEOUT_S) -> dict[str, Any]:
        self.end_audio()
        if not self._done.wait(timeout):
            self.cancel()
            return self._error("live transcription timed out")
        return dict(self._result)

    def cancel(self) -> None:
        self._cancelled.set()
        self._audio.put(None)
        self._finish(self._error("cancelled"))

    def partial_transcript(self) -> str:
        return self._partial

    # ── worker side ──
    def _set_partial(self, text: str) -> None:
        text = text.strip()
        if text and text != self._partial:
            self._partial = text
            if self._on_partial is not None:
                try:
                    self._on_partial(text)
                except Exception:
                    logger.debug("on_partial callback raised", exc_info=True)

    def _error(self, message: str) -> dict[str, Any]:
        return {"success": False, "transcript": "", "provider": self.provider, "error": message}

    def _finish(self, result: dict[str, Any]) -> None:
        if not self._done.is_set():
            self._result = result
            self._done.set()

    def _run(self) -> None:
        try:
            self._finish(self._session())
        except Exception as exc:  # health: allow BLE001 -- worker boundary: every failure becomes the envelope
            logger.warning("Live STT (%s) failed: %s", self.provider, exc, exc_info=True)
            self._finish(self._error(f"live transcription failed: {exc}"))

    def _session(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError


class _WebSocketSession(StreamingSession):
    """A provider wire over one websocket: subclasses map audio out and events in."""

    url = ""
    headers: dict[str, str] = {}

    def _session(self) -> dict[str, Any]:
        from websockets.sync.client import connect

        ws = connect(self.url, additional_headers=self.headers, open_timeout=_CONNECT_TIMEOUT_S,
                     close_timeout=1, max_size=None)
        try:
            return self._loop(ws)
        finally:
            # Publish first, close after: the sync close handshake waits up to close_timeout on a
            # server that already hung up, and the caller is blocked on finalize() meanwhile.
            spawn_context_thread(ws.close, name="stt-stream-close").start()

    def _loop(self, ws: Any) -> dict[str, Any]:
        self._open(ws)
        ending_since: Optional[float] = None
        while True:
            if self._cancelled.is_set():
                return self._error("cancelled")
            if ending_since is None:
                ending_since = self._drain_audio(ws)
            elif time.monotonic() - ending_since > _FINALIZE_TIMEOUT_S:
                return self._error("provider never finalized the transcript")
            try:
                raw = ws.recv(timeout=0.02)
            except TimeoutError:
                continue
            if isinstance(raw, (bytes, bytearray)):
                continue
            result = self._event(json.loads(raw))
            if result is not None:
                self._finish(result)
                return result

    def _drain_audio(self, ws: Any) -> Optional[float]:
        """Send queued audio; on end-of-audio send the provider's flush and return its time."""
        while True:
            chunk = self._take_audio(block=False)
            if chunk is None:
                self._end(ws)
                return time.monotonic()
            if not chunk:
                if self._audio.empty():
                    return None
                continue
            self._send_audio(ws, chunk)

    def _open(self, ws: Any) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _send_audio(self, ws: Any, chunk: bytes) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _end(self, ws: Any) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _event(self, event: dict[str, Any]) -> Optional[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError


class OpenAIRealtimeSession(_WebSocketSession):
    provider = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, language: Optional[str],
                 prompt: Optional[str], on_partial: Optional[PartialCallback] = None) -> None:
        super().__init__(on_partial)
        parts = urlsplit(base_url.rstrip("/"))
        scheme = "wss" if parts.scheme == "https" else "ws"
        self.url = urlunsplit((scheme, parts.netloc, f"{parts.path}/realtime", "intent=transcription", ""))
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.model, self.language, self.prompt = model, language, prompt
        self._resample = Resampler(INPUT_RATE, 24000)
        self._text = ""
        self._sent_audio = False

    def _open(self, ws: Any) -> None:
        transcription: dict[str, Any] = {"model": self.model}
        if self.language:
            # gpt-live-transcribe takes a ``languages`` list and rejects the singular field.
            if self.model == DEFAULT_OPENAI_STREAMING_MODEL:
                transcription["languages"] = [self.language]
            else:
                transcription["language"] = self.language
        if self.prompt:
            transcription["prompt"] = self.prompt
        ws.send(json.dumps({"type": "session.update", "session": {"type": "transcription", "audio": {"input": {
            "format": {"type": "audio/pcm", "rate": 24000}, "transcription": transcription,
            "turn_detection": None}}}}))

    def _send_audio(self, ws: Any, chunk: bytes) -> None:
        pcm = self._resample(chunk)
        if pcm:
            self._sent_audio = True
            ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()}))

    def _end(self, ws: Any) -> None:
        if not self._sent_audio:
            self._finish({"success": True, "transcript": "", "provider": self.provider})
            self._cancelled.set()
            return
        ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    def _event(self, event: dict[str, Any]) -> Optional[dict[str, Any]]:
        kind = str(event.get("type") or "")
        if kind.endswith("input_audio_transcription.delta"):
            self._text += str(event.get("delta") or "")
            self._set_partial(self._text)
        elif kind.endswith("input_audio_transcription.completed"):
            return {"success": True, "transcript": str(event.get("transcript") or self._text).strip(),
                    "provider": self.provider}
        elif kind == "error":
            message = str((event.get("error") or {}).get("message") or "provider error")
            # Committing < 100 ms of audio is "buffer too small": the user said nothing.
            if "buffer too small" in message.lower():
                return {"success": True, "transcript": "", "provider": self.provider}
            return self._error(message)
        return None


class _PluginSession(StreamingSession):
    """Adapts a plugin ``TranscriptionStreamSession`` to the caller API (partials polled)."""

    def __init__(self, provider_name: str, inner: Any, on_partial: Optional[PartialCallback]) -> None:
        super().__init__(on_partial)
        self.provider, self._inner = provider_name, inner

    def _session(self) -> dict[str, Any]:
        while True:
            chunk = self._take_audio(block=True, timeout=0.25)
            if self._cancelled.is_set():
                return self._error("cancelled")
            if chunk is None:
                return dict(self._inner.finalize())
            if chunk:
                self._inner.push_audio(chunk)
            self._set_partial(str(self._inner.partial_transcript() or ""))


# ── resolution ──

def streaming_enabled(stt_config: dict[str, Any]) -> bool:
    return is_truthy_value(stt_config.get("streaming", False), default=False)


def _openai_credentials() -> Optional[tuple[str, str]]:
    """Direct OpenAI credentials only: the managed Nous gateway proxies the REST audio API, not
    the Realtime socket."""
    from tools.tool_backend_helpers import NOUS_MANAGED_PROVIDER, read_selection
    from tools.transcription_tools import _resolve_openai_audio_client_config
    if read_selection("stt") == NOUS_MANAGED_PROVIDER:
        return None
    try:
        api_key, base_url = _resolve_openai_audio_client_config()
    except ValueError:
        return None
    return api_key, base_url


def _builtin_session(provider: str, stt_config: dict[str, Any], language: Optional[str],
                     prompt: Optional[str], on_partial: Optional[PartialCallback]) -> Optional[StreamingSession]:
    raw_section = stt_config.get(provider)
    section: dict[str, Any] = raw_section if isinstance(raw_section, dict) else {}
    if provider == "openai":
        creds = _openai_credentials()
        if creds is None:
            return None
        model = str(section.get("streaming_model") or DEFAULT_OPENAI_STREAMING_MODEL)
        return OpenAIRealtimeSession(creds[0], creds[1], model, language, prompt, on_partial)
    return None


def _plugin_session(provider: str, language: Optional[str], prompt: Optional[str],
                    on_partial: Optional[PartialCallback]) -> Optional[StreamingSession]:
    from agent.transcription_registry import get_provider
    registered = get_provider(provider)
    if registered is None or not registered.streaming_capable:
        return None
    return _PluginSession(provider, registered.open_stream_session(language=language, prompt=prompt), on_partial)


def streaming_available(stt_config: Optional[dict[str, Any]] = None) -> bool:
    """Cheap capability probe (no connection): would :func:`open_streaming_session` try a wire?"""
    from tools import transcription_tools as tt
    cfg = tt._load_stt_config() if stt_config is None else stt_config
    if not streaming_enabled(cfg):
        return False
    provider = tt._get_provider(cfg)
    if provider in STREAMING_PROVIDERS:
        return _builtin_session(provider, cfg, None, None, None) is not None
    from agent.transcription_registry import get_provider
    registered = get_provider(provider)
    return bool(registered is not None and registered.streaming_capable)


def open_streaming_session(on_partial: Optional[PartialCallback] = None,
                           stt_config: Optional[dict[str, Any]] = None) -> Optional[StreamingSession]:
    """Start a live STT session for the active profile's provider, or None (use the file path).

    None when ``stt.streaming`` is off, the provider has no live wire, or it lacks credentials.
    """
    from tools import transcription_tools as tt
    cfg = tt._load_stt_config() if stt_config is None else stt_config
    if not streaming_enabled(cfg):
        return None
    provider = tt._get_provider(cfg)
    if provider in ("none", "local", "local_command"):
        return None
    language = tt._resolve_stt_language(provider, cfg)
    prompt = str(cfg.get("prompt") or "").strip() or None
    try:
        if provider in STREAMING_PROVIDERS:
            session = _builtin_session(provider, cfg, language, prompt, on_partial)
        else:
            session = _plugin_session(provider, language, prompt, on_partial)
    except Exception:
        logger.warning("Live STT session for %s could not open", provider, exc_info=True)
        return None
    return session.start() if session is not None else None
