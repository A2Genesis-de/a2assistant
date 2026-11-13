"""Credential-level availability of the provider-backed tool categories for setup and status surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hermes_cli.config import get_env_value, load_config
from tools.tool_backend_helpers import (
    fal_key_is_configured, normalize_browser_cloud_provider, resolve_openai_audio_api_key,
)


@dataclass(frozen=True)
class ToolFeature:
    key: str
    label: str
    available: bool
    current_provider: str = ""


_BROWSER_LABELS = {
    "browserbase": "Browserbase", "browser-use": "Browser Use", "firecrawl": "Firecrawl", "local": "Local browser",
}


def _section(config: dict, key: str) -> dict:
    value = config.get(key)
    return value if isinstance(value, dict) else {}


def _norm(value: object, default: str = "") -> str:
    return str(value or default).strip().lower()


def _any_env(*names: str) -> bool:
    return any(get_env_value(name) for name in names)


def _has_browser_harness() -> bool:
    """browser_exec's engine (browser-harness) is importable: the only local requirement for a cloud
    browser provider, which hosts its own Chromium."""
    from tools.browser_use_cli import _find_cli

    return _find_cli() is not None


def _local_browser_runnable(browser_cfg: dict) -> bool:
    """True when the local browser would start: browser-harness plus ``lightpanda serve`` when
    ``browser.engine`` selects it, else a Chromium the launcher can run."""
    if not _has_browser_harness():
        return False
    if _norm(browser_cfg.get("engine"), "auto") == "lightpanda":
        return True
    from hermes_cli.browser_runtime import chromium_executable

    return chromium_executable() is not None


def _local_stt_backend_available() -> bool:
    """True when faster-whisper imports or a custom local STT command is configured."""
    if get_env_value("HERMES_LOCAL_STT_COMMAND"):
        return True
    try:
        from tools.transcription_tools import _HAS_FASTER_WHISPER

        return bool(_HAS_FASTER_WHISPER)
    except Exception:
        return False


def _web_feature(web_cfg: dict) -> ToolFeature:
    backend, search_backend, extract_backend = (
        _norm(web_cfg.get(k)) for k in ("backend", "search_backend", "extract_backend"))
    selected = {backend, search_backend, extract_backend}
    available = (
        _any_env("EXA_API_KEY", "PARALLEL_API_KEY", "PERPLEXITY_API_KEY", "SEARXNG_URL", "TAVILY_API_KEY",
                 "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL")
        or "tavily" in selected)
    return ToolFeature("web", "Web tools", available, backend or search_backend or extract_backend)


def _browser_feature(browser_cfg: dict) -> ToolFeature:
    explicit = "cloud_provider" in browser_cfg
    provider = normalize_browser_cloud_provider(browser_cfg.get("cloud_provider") if explicit else None)
    direct_browserbase = bool(get_env_value("BROWSERBASE_API_KEY") and get_env_value("BROWSERBASE_PROJECT_ID"))
    direct_browser_use = _any_env("BROWSER_USE_API_KEY")
    direct_firecrawl = _any_env("FIRECRAWL_API_KEY", "FIRECRAWL_API_URL")
    if explicit:
        cloud = {"browserbase": direct_browserbase, "browser-use": direct_browser_use, "firecrawl": direct_firecrawl}
        current = provider if provider in cloud else "local"
        available = (_has_browser_harness() and cloud[current]) if current in cloud else _local_browser_runnable(browser_cfg)
    elif direct_browser_use:
        current, available = "browser-use", _has_browser_harness()
    elif direct_browserbase:
        current, available = "browserbase", _has_browser_harness()
    else:
        current, available = "local", _local_browser_runnable(browser_cfg)
    return ToolFeature("browser", "Browser automation", bool(available), _BROWSER_LABELS.get(current, current))


def _tts_feature(tts_cfg: dict) -> ToolFeature:
    provider = _norm(tts_cfg.get("provider"), "edge")
    available = {
        "edge": True, "neutts": True, "openai": bool(resolve_openai_audio_api_key()),
        "elevenlabs": _any_env("ELEVENLABS_API_KEY"), "mistral": _any_env("MISTRAL_API_KEY"),
    }.get(provider, False)
    return ToolFeature("tts", "Text-to-speech", available, provider)


def _stt_feature(stt_cfg: dict) -> ToolFeature:
    provider = _norm(stt_cfg.get("provider"), "local")
    available = {
        "local": _local_stt_backend_available(), "openai": bool(resolve_openai_audio_api_key()),
        "groq": _any_env("GROQ_API_KEY"), "mistral": _any_env("MISTRAL_API_KEY"),
    }.get(provider, False)
    return ToolFeature("stt", "Speech-to-text", available, provider)


def get_tool_features(config: Optional[dict] = None) -> dict[str, ToolFeature]:
    """Category key -> availability from the user's own credentials and local installs."""
    if config is None:
        config = load_config() or {}
    fal = fal_key_is_configured()
    return {
        "web": _web_feature(_section(config, "web")),
        "image_gen": ToolFeature("image_gen", "Image generation", fal, "FAL" if fal else ""),
        "video_gen": ToolFeature("video_gen", "Video generation", fal, "FAL" if fal else ""),
        "tts": _tts_feature(_section(config, "tts")),
        "stt": _stt_feature(_section(config, "stt")),
        "browser": _browser_feature(_section(config, "browser")),
    }
