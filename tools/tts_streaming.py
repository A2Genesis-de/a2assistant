"""Provider-agnostic streaming TTS: sentence text → int16 mono PCM chunk iterator.

``stream_tts_to_speaker`` (``tools.tts_tool``) owns the sentence buffer, sounddevice
output and stop/queue protocol; this module owns the *provider* half so playback
starts on sentence one. True streamers (``StreamingTTSProvider.stream``) wrap chunked
APIs; providers with no chunked API (command, local engines) get per-sentence playback via
the sync ``text_to_speech_tool`` path. Adding a streamer is ``@register("name")`` on
a subclass; the dispatcher, config gate (``tts.<name>.streaming``) and resolver come free.
Plugin ``TTSProvider``s join by declaring ``streams_pcm`` + ``stream_sample_rate``.
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator, Optional

from agent.think_scrubber import THINK_TAG_NAMES
from tools.tool_backend_helpers import resolve_openai_audio_api_key
from tools.tts_tool import _get_provider, _load_tts_config
from tools.tts_tool_plugins import _plugin_pcm_streaming_provider, _plugin_voice_kwargs

logger = logging.getLogger(__name__)

# Per-sentence PCM byte cap, mirroring the sync providers' 16 MiB bounded-body invariant.
_STREAM_SENTENCE_BYTE_CAP = 16 * 1024 * 1024


# Interruption latch: a barge-in on a spoken reply marks it; the next turn's submit path takes it
# and prepends SPEECH_INTERRUPTED_NOTE to the model-bound message (API-call local, never
# persisted). The TTL keeps a stale barge from annotating an unrelated message minutes later.
SPEECH_INTERRUPTED_NOTE = "[Note: the user interrupted your previous spoken reply before it finished.]"
_INTERRUPT_TTL_S = 120.0
_interrupted_at: Optional[float] = None


def mark_speech_interrupted() -> None:
    global _interrupted_at
    _interrupted_at = time.monotonic()


def take_speech_interrupted() -> bool:
    """Pop the latch; True when a barge happened within the TTL."""
    global _interrupted_at
    at, _interrupted_at = _interrupted_at, None
    return at is not None and time.monotonic() - at < _INTERRUPT_TTL_S

# Sentence boundary: after .!? followed by whitespace, or a blank line.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s|\n)|(?:\n\n)")
# Reasoning tags come from the one canonical list (agent.think_scrubber), matched case-insensitively,
# so feed() and flush() strip/cut exactly the tags every other reasoning-hiding surface does.
_THINK_NAMES = "|".join(re.escape(name) for name in THINK_TAG_NAMES)
_THINK_BLOCK_RE = re.compile(rf"<({_THINK_NAMES})[\s>].*?</\1>", flags=re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(rf"<(?:{_THINK_NAMES})(?=[\s>]|$)", flags=re.IGNORECASE)


class SentenceChunker:
    """Incremental sentence cutter for LLM token deltas, shared by the speaker pipeline and the
    speak-stream WebSocket so every surface cuts speech identically. Strips ``<think>`` blocks (even
    split across deltas) and merges fragments shorter than *min_len* into the following sentence."""

    def __init__(self, min_len: int = 20):
        self.min_len = min_len
        self.buf = ""

    @classmethod
    def from_config(cls, tts_config: dict) -> SentenceChunker:
        """Chunker honouring ``tts.streaming.min_len``. 20 suits English; a CJK opener of 5–7
        characters is a whole clause, so voice setups lower it to speak the first sentence
        alone instead of buffering it behind the second. Floor 1: 0 would emit every boundary."""
        try:
            return cls(min_len=max(1, int((tts_config.get("streaming") or {}).get("min_len", 20))))
        except (AttributeError, TypeError, ValueError):  # non-mapping / non-numeric → default
            return cls()

    def feed(self, delta: str) -> list[str]:
        """Absorb *delta*; return every complete sentence now ready to speak."""
        self.buf = _THINK_BLOCK_RE.sub("", self.buf + delta)
        if _THINK_OPEN_RE.search(self.buf):
            return []  # open think tag — the closing tag may arrive next delta
        out: list[str] = []
        start = 0  # skip boundaries that would leave the head too short
        while m := SENTENCE_BOUNDARY_RE.search(self.buf, start):
            head = self.buf[: m.end()]
            if len(head.strip()) < self.min_len:
                start = m.end()
                continue
            out.append(head)
            self.buf = self.buf[m.end():]
            start = 0
        return out

    def flush(self) -> list[str]:
        """Drain the tail (end-of-text or long-idle flush)."""
        tail, self.buf = _THINK_BLOCK_RE.sub("", self.buf), ""
        if m := _THINK_OPEN_RE.search(tail):
            tail = tail[: m.start()]  # unterminated reasoning block: never speak it
        tail = tail.strip()
        return [tail] if tail else []


class StreamingTTSProvider(ABC):
    """Yields raw int16, little-endian, mono PCM chunks at ``sample_rate`` (built-ins: 24 kHz).

    ``sample_rate`` is provisional until ``stream()`` has yielded its first chunk: a provider may
    update the instance attribute once the endpoint's real format is known (OpenAI-compatible
    servers advertise it in the response headers), so consumers open their output device or WAV
    header after pulling the first chunk, never at construction.
    """

    sample_rate: int = 24000
    channels: int = 1
    sample_width: int = 2  # bytes/sample (int16)

    def __init__(self, tts_config: dict, section: dict):
        self.tts_config = tts_config
        self.section = section

    @staticmethod
    @abstractmethod
    def available() -> bool:
        """True when this provider's credentials/SDK are usable right now."""

    @abstractmethod
    def stream(self, text: str) -> Iterator[bytes]:
        """Yield PCM chunks for ``text``. Raise on failure (caller logs)."""


_REGISTRY: dict[str, type[StreamingTTSProvider]] = {}


def register(name: str) -> Callable[[type[StreamingTTSProvider]], type[StreamingTTSProvider]]:
    def _wrap(cls: type[StreamingTTSProvider]) -> type[StreamingTTSProvider]:
        _REGISTRY[name] = cls
        return cls
    return _wrap


def _try_instantiate(name: str, tts_config: dict) -> Optional[StreamingTTSProvider]:
    """Construct the registered streamer *name* if it's usable, else None."""
    cls = _REGISTRY.get(name)
    if cls is None or not cls.available():
        return None
    try:
        return cls(tts_config, tts_config.get(name) or {})
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("streaming provider %s init failed: %s", name, exc)
        return None


_PROVIDER_PRIORITY: list[str] = ["openai"]


class _PluginPCMStreamer(StreamingTTSProvider):
    """A plugin ``TTSProvider`` that opted into raw PCM (``streams_pcm``; see
    ``tools.tts_tool_plugins._plugin_pcm_streaming_provider``) behind this ABC."""

    def __init__(self, provider: Any, sample_rate: int, tts_config: dict):
        super().__init__(tts_config, tts_config.get(provider.name) or {})
        self._provider, self.sample_rate = provider, sample_rate

    @staticmethod
    def available() -> bool:
        return True  # gated at resolve time, per instance

    def stream(self, text: str) -> Iterator[bytes]:
        yield from _capped(
            self._provider.stream(text, format="pcm", **_plugin_voice_kwargs(self.tts_config)),
            f"plugin streamer {self._provider.name}")


def _plugin_streamer(name: str, tts_config: dict) -> Optional[StreamingTTSProvider]:
    found = _plugin_pcm_streaming_provider(name, tts_config)
    return _PluginPCMStreamer(*found, tts_config) if found is not None else None


def resolve_streaming_provider(
    tts_config: dict, preferred: Optional[str] = None) -> Optional[StreamingTTSProvider]:
    """Return a ready streamer for the *configured* provider, else ``None``.
    ``tts.streaming.provider`` when set: a name pins that exact streamer (``None`` if unusable);
    ``auto`` returns the first usable in ``_PROVIDER_PRIORITY``. Otherwise the configured TTS
    provider (or ``preferred``): ``None`` means "no chunked API" — the dispatcher speaks
    per-sentence via the sync path, preserving the user's chosen voice. We never silently swap
    providers just to get streaming.

    A plugin ``TTSProvider`` that opted into raw PCM (``streams_pcm``) streams here too, after the
    built-ins and under the same rules (a pinned name never substitutes another voice)."""
    pinned = str((tts_config.get("streaming") or {}).get("provider") or "").lower().strip()
    if pinned == "auto":
        for name in _PROVIDER_PRIORITY:
            if (inst := _try_instantiate(name, tts_config)) is not None:
                return inst
        return _plugin_streamer(_get_provider(tts_config), tts_config)
    name = pinned or (preferred or _get_provider(tts_config)).lower().strip()
    return _try_instantiate(name, tts_config) or _plugin_streamer(name, tts_config)


def _capped(chunks: Iterator[bytes], label: str) -> Iterator[bytes]:
    """Pass chunks through, aborting past the per-sentence byte cap (runaway/hostile upstream)."""
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > _STREAM_SENTENCE_BYTE_CAP:
            logger.warning("%s exceeded %d bytes for one sentence; truncating", label, _STREAM_SENTENCE_BYTE_CAP)
            return
        yield chunk


def _openai_config_api_key() -> str:
    """Return ``tts.openai.api_key`` from config.yaml, or empty string."""
    try:
        return (_load_tts_config().get("openai") or {}).get("api_key") or ""
    except Exception:
        return ""


def _sample_rate_from_headers(headers) -> Optional[int]:
    """Rate an OpenAI-compatible TTS endpoint advertises: ``X-Audio-Sample-Rate`` (the convention
    local servers use) or ``rate=`` in ``Content-Type`` (``audio/pcm; rate=44100``); None if absent."""
    if not headers:
        return None
    raw = headers.get("x-audio-sample-rate")
    if raw is None:
        m = re.search(r"(?:^|[;\s])rate\s*=\s*(\d+)", str(headers.get("content-type") or ""), re.IGNORECASE)
        raw = m.group(1) if m else None
    try:
        rate = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


@register("openai")
class OpenAIStreamer(StreamingTTSProvider):
    """OpenAI speech with ``response_format=pcm`` (OpenAI itself: 24 kHz mono int16).

    Compatible servers may emit another rate: ``tts.openai.pcm_sample_rate`` sets the expected
    rate up front and a rate reported by the response (``X-Audio-Sample-Rate`` / Content-Type
    ``rate=``) overrides it before the first chunk is yielded (#76466).
    """

    def __init__(self, tts_config: dict, section: dict):
        super().__init__(tts_config, section)
        configured = section.get("pcm_sample_rate", self.sample_rate)
        if isinstance(configured, bool) or not isinstance(configured, (int, float, str)) \
                or not str(configured).strip().isdigit() or int(str(configured).strip()) <= 0:
            logger.warning("Invalid tts.openai.pcm_sample_rate %r; using %d Hz", configured, self.sample_rate)
        else:
            self.sample_rate = int(str(configured).strip())

    @staticmethod
    def available() -> bool:
        return bool(_openai_config_api_key() or resolve_openai_audio_api_key())

    def stream(self, text: str) -> Iterator[bytes]:
        from openai import OpenAI
        from hermes_cli.config import get_env_value
        client = OpenAI(
            api_key=(self.section.get("api_key") or resolve_openai_audio_api_key()),
            base_url=(self.section.get("base_url") or get_env_value("OPENAI_BASE_URL") or None))
        from tools.tts_tool_openai import _openai_extra_body
        extra = {"extra_body": body} if (body := _openai_extra_body(self.section)) else {}
        with client.audio.speech.with_streaming_response.create(
            model=self.section.get("model", "gpt-4o-mini-tts"), voice=self.section.get("voice", "alloy"),
            input=text, response_format="pcm", **extra,
        ) as response:
            # Runs on the first next(), before any audio is yielded, so consumers reading
            # ``sample_rate`` after the first chunk open their device at the endpoint's rate.
            rate = _sample_rate_from_headers(getattr(response, "headers", None))
            if rate is not None and rate != self.sample_rate:
                logger.info("TTS endpoint reports %d Hz PCM (expected %d Hz); honoring it", rate, self.sample_rate)
                self.sample_rate = rate
            yield from _capped(response.iter_bytes(), "OpenAI streaming TTS")
