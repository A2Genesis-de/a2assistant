"""OpenAI-compatible cloud STT.

The OpenAI ``audio.transcriptions`` backend and OpenAI audio credential resolution (config >
keyless local server > env > managed Nous gateway). Facade-owned state and helpers
(``_HAS_OPENAI``, ``_resolve_stt_language``, ``_load_stt_config``) are read lazily from
``tools.transcription_tools``.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

from tools.transcription_audio import _transcode_audio_for_stt
from tools.transcription_common import (
    OPENAI_BASE_URL, STTResponseError, _error_result, _get_stt_section, _ok_result)

# Log-record parity with the origin module.
logger = logging.getLogger("tools.transcription_tools")
# Voxtral-style ``language xx <asr_text> ...`` prefix some SDK responses carry.
_ASR_TEXT_RE = re.compile(
    r"\s*language\s+[\w.-]+(?:\s*<audio_language>[^<]*</audio_language>)?\s*<asr_text>\s*(?P<text>.*)",
    flags=re.IGNORECASE | re.DOTALL)


def _with_openai_client(api_key: str, base_url: Optional[str], file_path: str, log_label: str, body):
    """Run ``body(client)`` on a fresh OpenAI SDK client; always closed. Transport shape comes from
    ``stt.openai.timeout`` / ``stt.openai.max_retries`` (defaults 60s, 1 retry; #112939) because a self-hosted endpoint's model cold
    start exceeds the old fixed 30s and lost the voice message at the first attempt.
    Errors map to the shared envelope. APIConnectionError is checked before APITimeoutError (its
    subclass) so timeouts report as connection errors, as they always have."""
    try:
        from openai import OpenAI
        from tools.transcription_common import DEFAULT_STT_TIMEOUT, _config_number
        from tools.transcription_tools import _load_stt_config
        openai_config = _get_stt_section(_load_stt_config(), "openai")
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_config_number(openai_config, "timeout", DEFAULT_STT_TIMEOUT),
            max_retries=_config_number(openai_config, "max_retries", 1, cast=int),
        )
        try:
            return body(client)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        try:
            from openai import APIError, APIConnectionError, APITimeoutError
        except ImportError:  # pragma: no cover — callers gate on _HAS_OPENAI
            APIError = APIConnectionError = APITimeoutError = ()
        if isinstance(exc, PermissionError):
            return _error_result(f"Permission denied: {file_path}")
        if isinstance(exc, STTResponseError):
            # The provider's own message already reads as an error; no "Transcription failed:" prefix.
            return _error_result(str(exc))
        for cls, label in ((APIConnectionError, "Connection error"), (APITimeoutError, "Request timeout"),
                           (APIError, "API error")):
            if isinstance(exc, cls):
                return _error_result(f"{label}: {exc}")
        logger.error("%s transcription failed: %s", log_label, exc, exc_info=True)
        return _error_result(f"Transcription failed: {exc}")


def _transcribe_openai(
    file_path: str, model_name: str, *, api_key: Optional[str] = None,
    base_url: Optional[str] = None, language: Optional[str] = None,
    prompt: Optional[str] = None) -> dict[str, Any]:
    """Transcribe via the OpenAI ``audio.transcriptions.create`` SDK shape (OpenAI or any
    OpenAI-compatible endpoint): explicit ``api_key``/``base_url`` skip the auth chain."""
    from tools.transcription_tools import _HAS_OPENAI, _resolve_stt_language
    if api_key is None:
        try:
            api_key, fallback_base = _resolve_openai_audio_client_config()
        except ValueError as exc:
            return _error_result(str(exc))
        base_url = base_url or fallback_base
    # Language: hook override > stt.openai.language > stt.language > env > auto.
    language = language or _resolve_stt_language("openai")
    if not _HAS_OPENAI:
        return _error_result("openai package not installed")

    def _run(client):
        from openai import APIStatusError

        def _create_transcription(path: str):
            create_kwargs: dict[str, Any] = {
                "model": model_name, "response_format": "text" if model_name == "whisper-1" else "json",
            }
            if language:
                # gpt-transcribe takes a ``languages`` list and rejects the legacy field.
                if model_name == "gpt-transcribe":
                    create_kwargs["extra_body"] = {"languages": [language]}
                else:
                    create_kwargs["language"] = language
                logger.debug("Using language hint '%s' for OpenAI STT", language)
            if prompt:  # only when set so the bare request stays byte-identical
                create_kwargs["prompt"] = prompt
            with open(path, "rb") as audio_file:
                return client.audio.transcriptions.create(file=audio_file, **create_kwargs)
        with tempfile.TemporaryDirectory(prefix="hermes-stt-") as work_dir:
            try:
                transcription = _create_transcription(file_path)
            except APIStatusError as exc:
                # 400 + container hint is the documented rejection; some OpenAI-compatible endpoints
                # reject a container with a bare 5xx instead (#81644). A 5xx is ambiguous, so it earns
                # the same single transcode retry and, when no transcode is possible, its own error.
                is_server_error = (exc.status_code or 0) >= 500
                if not is_server_error and not any(k in str(exc).lower() for k in ("unsupported", "corrupted", "invalid file")):
                    raise
                # Newer models reject containers whisper-1 accepted (Ogg/Opus voice notes): transcode, retry once.
                converted_path, transcode_error = _transcode_audio_for_stt(file_path, work_dir)
                if transcode_error:
                    if is_server_error:
                        raise
                    return _error_result(transcode_error)
                logger.info("Retrying openai STT after transcoding %s to m4a (API rejected the original container)",
                            Path(file_path).name)
                transcription = _create_transcription(converted_path)
        transcript_text = _extract_transcript_text(transcription)
        logger.info("Transcribed %s via openai (%s, %d chars)",
                    Path(file_path).name, model_name, len(transcript_text))
        return _ok_result(transcript_text, "openai")
    return _with_openai_client(api_key, base_url, file_path, "openai", _run)


# ---- OpenAI audio credential resolution -----------------------------------
def _is_local_or_private_url(url: str) -> bool:
    """True for loopback/RFC-1918/LAN-internal hosts, where an empty ``stt.openai.api_key`` is acceptable
    (local OpenAI-compatible servers ignore the auth header — no sham ``api_key: not-needed`` needed)."""
    try:
        from urllib.parse import urlparse
        import ipaddress
        host = (urlparse(url).hostname or "").lower()
        if host == "localhost" or host.endswith((".local", ".lan", ".internal")):
            return True
        addr = ipaddress.ip_address(host)  # raises for "" and non-IP hostnames
        return addr.is_private or addr.is_loopback
    except Exception:  # unparsable URL or non-IP hostname
        return False


def _direct_openai_credentials(cfg_api_key: str, cfg_base_url: str) -> Optional[tuple[str, str]]:
    """Direct-credential ladder: config key > keyless local base_url (placeholder key so the SDK
    constructs a client) > env key; None if none apply."""
    from tools.tool_backend_helpers import resolve_openai_audio_api_key
    if cfg_api_key:
        return cfg_api_key, (cfg_base_url or OPENAI_BASE_URL)
    # A local OpenAI-compatible server needs no key — send a placeholder so the SDK doesn't refuse to
    # construct a client (#25193, credit @nnnet).
    if cfg_base_url and _is_local_or_private_url(cfg_base_url):
        return "not-needed", cfg_base_url
    direct_api_key = resolve_openai_audio_api_key()
    return (direct_api_key, OPENAI_BASE_URL) if direct_api_key else None


def _resolve_openai_audio_client_config() -> tuple[str, str]:
    """``(api_key, base_url)`` for the OpenAI STT client, strict on the stored ``stt`` selection:
    ``"nous"`` -> managed gateway ONLY (a direct OPENAI_API_KEY must NOT override it); any other
    stored provider -> direct credentials ONLY (no silent managed fallback); never-configured ->
    legacy ladder: direct credentials, then the managed gateway. Failures raise ValueError."""
    from tools.transcription_tools import _load_stt_config
    from tools.managed_tool_gateway import resolve_managed_tool_gateway
    from tools.tool_backend_helpers import (
        NOUS_MANAGED_PROVIDER, managed_nous_tools_enabled, nous_tool_gateway_unavailable_message,
        read_selection, selection_error)
    openai_cfg = _load_stt_config().get("openai") or {}
    selected = read_selection("stt")

    def _managed() -> Optional[tuple[str, str]]:
        gateway = resolve_managed_tool_gateway("openai-audio")
        if gateway is None:
            return None
        return gateway.nous_user_token, urljoin(f"{gateway.gateway_origin.rstrip('/')}/", "v1")

    if selected == NOUS_MANAGED_PROVIDER:
        managed = _managed()
        if managed is None:
            raise ValueError(selection_error("stt", NOUS_MANAGED_PROVIDER,
                                             "the Nous Tool Gateway is not available (not entitled or unreachable)"))
        return managed
    direct = _direct_openai_credentials(openai_cfg.get("api_key", ""), openai_cfg.get("base_url", ""))
    if direct is not None:
        return direct
    if selected is not None:
        raise ValueError(selection_error(
            "stt", selected,
            "neither stt.openai.api_key in config nor VOICE_TOOLS_OPENAI_KEY/OPENAI_API_KEY is set"))
    managed = _managed()
    if managed is None:
        message = "Neither stt.openai.api_key in config nor VOICE_TOOLS_OPENAI_KEY/OPENAI_API_KEY is set"
        if managed_nous_tools_enabled():
            message += ". " + nous_tool_gateway_unavailable_message("managed OpenAI audio for transcription")
        raise ValueError(message)
    return managed


def _extract_transcript_text(transcription: Any) -> str:
    """Normalize text / object / dict transcription responses to a plain string.

    A *structured* response (SDK object or JSON dict) whose ``text`` is missing or
    non-string must never reach ``str(transcription)``: that renders the object repr
    (``Transcription(text=None, logprobs=None, usage=None, error='...')``), which
    every caller then logged and returned as a successful transcript, and the desktop
    injected as the user's message (#78098). Such a response raises its provider
    ``error`` instead, so the callers' existing failure paths report it; a structured
    response carrying neither text nor error is an error in its own right.
    Unrecognized scalars keep the legacy stringification."""
    if isinstance(transcription, str):
        text = transcription.strip()
    else:
        is_mapping = isinstance(transcription, dict)
        value = transcription.get("text") if is_mapping else getattr(transcription, "text", None)
        if isinstance(value, str):
            text = value.strip()
        elif is_mapping or hasattr(transcription, "text"):
            error = transcription.get("error") if is_mapping else getattr(transcription, "error", None)
            raise STTResponseError(str(error) if error else "Transcription response contained no text")
        else:
            text = str(transcription).strip()
    match = _ASR_TEXT_RE.match(text)
    return match.group("text").strip() if match else text
