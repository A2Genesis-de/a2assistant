"""Resolve the active profile's STT/TTS config for CLIENT-DIRECT voice.

Single resolver behind ``GET /api/audio/voice-config``: the desktop skips the
audio relay hop by calling providers directly with the profile's own
credentials, resolved through the exact chains of ``tools.transcription_tools``
and ``tools.tts_tool`` so the client gets byte-for-byte what the gateway uses.
Rules: same trust boundary as every REST route (keys never logged, never hit
client disk); relay is the floor, not an error (server-host-only providers and
resolution failures return ``{"mode": "relay"}``); no new key stores.
Config gate: ``voice.client_direct`` (default ``true``).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Wire shapes the desktop knows how to speak. Anything else → relay.
#   openai-multipart : POST {base_url}/audio/transcriptions (multipart, Bearer)
#   openai-speech    : POST {base_url}/audio/speech (JSON, Bearer) → audio bytes
STT_WIRE_OPENAI = "openai-multipart"
TTS_WIRE_OPENAI = "openai-speech"


def _client_direct_enabled() -> bool:
    try:
        from hermes_cli.config import load_config
        voice_cfg = load_config().get("voice") or {}
        if not isinstance(voice_cfg, dict):
            return True
        value = voice_cfg.get("client_direct", True)
    except Exception:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return True


def _relay(reason: str) -> dict[str, Any]:
    """A relay verdict that tells the client WHY, without secrets."""
    return {"mode": "relay", "reason": reason}


def _section(config: Any, provider: str) -> dict[str, Any]:
    """The provider's own sub-dict of an STT/TTS config, shape-guarded."""
    section = config.get(provider) if isinstance(config, dict) else None
    return section if isinstance(section, dict) else {}


def _direct(wire: str, provider: str, base_url: Any, api_key: str, model: Any, **extra: Any) -> dict[str, Any]:
    return {"mode": "direct", "wire": wire, "provider": provider, "base_url": base_url,
            "api_key": api_key, "model": model, **extra}


def stt_hallucination_filter() -> dict[str, Any]:
    """The Whisper-silence hallucination contract the relay path applies
    (``transcribe_recording`` → ``is_whisper_hallucination``), shipped to the
    client so a client-direct transcription agrees with a relayed one instead
    of submitting "thank you" on silence as a real turn."""
    from tools.voice_mode_transcript import WHISPER_HALLUCINATIONS

    return {
        "phrases": sorted(WHISPER_HALLUCINATIONS),
        # Python's _HALLUCINATION_REPEAT_RE (IGNORECASE) for repetitive filler
        # like "OK. OK. OK." — a JS regex source, so a single backslash.
        "repeat_regex": "^(?:thank you|thanks|bye|you|ok|okay|the end|[.,!\\s])+$",
    }


# ── STT ──
def _resolve_stt_client_config() -> dict[str, Any]:
    from tools import transcription_common as tc
    from tools import transcription_tools as tt

    stt_config = tt._load_stt_config()
    if not tt.is_stt_enabled(stt_config):
        return _relay("stt disabled")
    provider = tt._get_provider(stt_config)
    # Server-host-only: local whisper, the env-var command escape hatch,
    # declared command providers, and anything plugin-registered.
    if tt._is_local_stt_provider(provider, stt_config):
        return _relay("local provider")
    if provider not in tc.BUILTIN_STT_PROVIDERS:
        return _relay("command/plugin provider")

    language = tt._resolve_stt_language(provider, stt_config)
    section = _section(stt_config, provider)
    # Same deadline the gateway's own transcription client applies (``stt.openai.timeout``),
    # so a slow endpoint fails the Desktop's direct request instead of hanging it.
    timeout_s = tc._config_number(_section(stt_config, "openai"), "timeout", 60.0)

    if provider == "openai":
        # Covers the Nous-managed selection too: the resolver returns the user's
        # own gateway token + managed base URL — exactly what the client should use.
        try:
            api_key, base_url = tt._resolve_openai_audio_client_config()
        except ValueError as exc:
            return _relay(f"openai resolution failed: {exc}")
        return _direct(STT_WIRE_OPENAI, provider, base_url, api_key, section.get("model") or tc.DEFAULT_STT_MODEL,
                       language=language, timeout_s=timeout_s, hallucination_filter=stt_hallucination_filter())
    return _relay(f"provider {provider!r} has no client wire")


# ── TTS ──
def _resolve_tts_client_config() -> dict[str, Any]:
    from tools import tts_tool as tts
    from tools import tts_tool_openai

    tts_config = tts._load_tts_config()
    provider = tts._get_provider(tts_config)
    if provider not in tts.BUILTIN_TTS_PROVIDERS:
        return _relay("command/plugin provider")
    # The desktop's client-direct sentence cutter honours the same tts.streaming.min_len as
    # the gateway/CLI chunkers, so a short CJK opener is spoken alone on every surface.
    from tools.tts_streaming import SentenceChunker
    min_len = SentenceChunker.from_config(tts_config).min_len

    if provider == "openai":
        # Covers the direct-key, custom-base_url, and Nous-managed selections.
        try:
            api_key, base_url, is_managed = tts_tool_openai._resolve_openai_audio_client_config()
        except ValueError as exc:
            return _relay(f"openai resolution failed: {exc}")
        oai = _section(tts_config, "openai")
        model = oai.get("model") or tts_tool_openai.DEFAULT_OPENAI_MODEL
        config_base = oai.get("base_url")
        base_url = config_base or base_url
        # The managed gateway only proxies MANAGED_OPENAI_TTS_MODELS — same
        # coercion text_to_speech applies server-side.
        if is_managed and not config_base and model not in tts_tool_openai.MANAGED_OPENAI_TTS_MODELS:
            model = tts_tool_openai.DEFAULT_OPENAI_MODEL
        speed_default = tts_config.get("speed", 1.0) if isinstance(tts_config, dict) else 1.0
        try:
            speed = float(oai.get("speed", speed_default))
        except (TypeError, ValueError):
            speed = 1.0
        return _direct(TTS_WIRE_OPENAI, "openai", base_url, api_key, model,
                       voice=oai.get("voice") or tts_tool_openai.DEFAULT_OPENAI_VOICE, speed=speed,
                       extra_body=tts_tool_openai._openai_extra_body(oai),
                       min_len=min_len)
    # kittentts / piper: server-host-only engines; the relay path serves them.
    return _relay(f"provider {provider!r} has no client wire")


def resolve_client_voice_config(client_direct: bool = True) -> dict[str, Any]:
    """Resolve both directions for the CURRENT profile scope.

    Callers scope the profile via ``hermes_constants.set_hermes_home_override``
    (the web server's ``_config_profile_scope``) before calling — identical to
    how ``/api/audio/transcribe`` scopes ``transcribe_recording``.
    ``client_direct=False`` is the serving surface's verdict (a browser tab):
    both directions relay and no key is resolved.
    """
    out: dict[str, Any] = {}
    if not client_direct:
        out = {"stt": _relay("browser surface"), "tts": _relay("browser surface")}
    elif not _client_direct_enabled():
        out = {"stt": _relay("voice.client_direct disabled"), "tts": _relay("voice.client_direct disabled")}
    else:
        for key, resolver in (("stt", _resolve_stt_client_config), ("tts", _resolve_tts_client_config)):
            try:
                out[key] = resolver()
            except Exception:
                logger.exception("client voice-config %s resolution failed", key.upper())
                out[key] = _relay("resolution error")
    # Live dictation always goes through the host's /api/audio/transcribe-stream socket (keys stay
    # server-side), independent of client_direct; the verdict above remains the blob fallback.
    from tools.transcription_streaming import streaming_available
    try:
        out["stt"]["streaming"] = streaming_available()
    except Exception:
        logger.debug("live STT capability probe failed", exc_info=True)
    return out
