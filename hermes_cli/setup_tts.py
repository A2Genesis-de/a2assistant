"""Text-to-speech provider setup (provider picker, API-key prompt, local engine installs, xAI OAuth).
setup.py names are resolved through the module object so test patches on ``hermes_cli.setup.<name>``
take effect; setup.py re-exports the public entry points."""

import logging
from tools import tool_backend_helpers

logger = logging.getLogger("hermes_cli.setup")

DEFAULT_TTS_PROVIDER = "openai"


def _install_tts_extra(extra: str) -> bool:
    """Record the engine in PM's dependency union; activate it on next launch."""
    import pm

    try:
        pm.sync_venv([extra], explicit=True)
    except (pm.InstallError, OSError, ValueError) as exc:
        _setup.print_error(f"Failed to install {extra}: {exc}")
        _setup.print_info("Retry with: hermes setup tts")
        return False
    _setup.print_success(f"{extra} installed. Restart A2Assistant to use it.")
    return True


def _install_kittentts_deps() -> bool:
    """Install KittenTTS dependencies with user approval. Returns True on success."""
    _setup._info(None, "Installing kittentts Python package (~25-80MB model downloaded on first use)...", None)
    return _install_tts_extra("kittentts")


def _run_xai_oauth_login_from_setup() -> bool:
    """Run the xAI Grok OAuth device-code login from inside the setup wizard. Saves OAuth tokens
    only — does **not** switch the active provider or rewrite ``model.provider`` (callers only need
    credentials for side tools). False on any failure (caller falls back)."""
    try:
        from hermes_cli.auth import (
            _is_remote_session, _save_xai_oauth_tokens, _xai_oauth_device_code_login,
            unsuppress_credential_source)
    except Exception as exc:
        _setup.print_warning(f"xAI Grok OAuth helpers unavailable: {exc}")
        return False
    _setup._info(None, "Signing in to xAI Grok OAuth (SuperGrok / Premium+)...")
    try:
        creds = _xai_oauth_device_code_login(open_browser=not _is_remote_session())
        _save_xai_oauth_tokens(
            creds["tokens"], discovery=creds.get("discovery"), redirect_uri=creds.get("redirect_uri", ""),
            last_refresh=creds.get("last_refresh"), auth_mode="oauth_device_code", set_active=False)
        # Mirror model/dashboard re-login: clear device_code suppression so the pool can seed
        # from the singleton after a prior `auth remove`.
        unsuppress_credential_source("xai-oauth", "device_code")
        return True
    except Exception as exc:
        _setup.print_warning(f"xAI Grok OAuth login failed: {exc}")
        return False


_TTS_PROVIDER_CHOICES = [
    ("openai", "OpenAI-compatible TTS (OpenAI or a self-hosted endpoint, needs API key)"),
    ("kittentts", "KittenTTS (local on-device, free, lightweight ~25-80MB ONNX)")]
# Short label = menu label minus its parenthetical ("OpenAI-compatible TTS", "KittenTTS").
_TTS_PROVIDER_LABELS = {key: label.split(" (")[0] for key, label in _TTS_PROVIDER_CHOICES}
_OPENAI_KEY_ENV_VARS = ("VOICE_TOOLS_OPENAI_KEY", "OPENAI_API_KEY")
# provider -> (module, display name, requirement lines, install question, installer)
_TTS_LOCAL_PROVIDERS = {
    "kittentts": ("kittentts", "KittenTTS",
                  ("KittenTTS is lightweight (~25-80MB, CPU-only, no API key required).",
                   "Voices: Jasper, Bella, Luna, Bruno, Rosie, Hugo, Kiki, Leo"),
                  "Install KittenTTS now?", _install_kittentts_deps)}


def _tts_openai_key_step() -> str:
    """Ensure an OpenAI audio key exists; the selection is kept either way."""
    if any(_setup.get_env_value(v) for v in _OPENAI_KEY_ENV_VARS):
        return "openai"
    print()
    api_key = _setup.prompt("OpenAI API key for TTS", password=True)
    if api_key:
        _setup.save_env_value("VOICE_TOOLS_OPENAI_KEY", api_key)
        _setup.print_success("OpenAI TTS API key saved")
    else:
        _setup.print_warning("No API key provided. Set VOICE_TOOLS_OPENAI_KEY before using speech output.")
    return "openai"


def _tts_local_install_step(selected: str) -> str:
    """Offer a local engine install; retain an unsupported explicit selection."""
    from pm.extras import extra_supported

    module, name, lines, question, installer = _TTS_LOCAL_PROVIDERS[selected]
    if not extra_supported(selected):
        _setup.print_warning(
            f"{name} is not supported by this Python/platform. "
            "Your provider selection is saved, but speech requires a supported engine.")
        return selected
    if _setup._module_installed(module):
        _setup.print_success(f"{name} is already installed")
        return selected
    print()
    for line in lines:
        _setup.print_info(line)
    print()
    if not _setup.prompt_yes_no(question, True):
        _setup.print_info(f"Skipping install. Set tts.provider to '{selected}' after installing manually.")
        return DEFAULT_TTS_PROVIDER
    if not installer():
        _setup.print_warning(f"{name} installation incomplete. Falling back to OpenAI-compatible TTS.")
        return DEFAULT_TTS_PROVIDER
    return selected


def _setup_tts_provider(config: dict):
    """Interactive TTS provider selection with install flow for local engines."""
    from hermes_cli import nous_subscription
    current_provider = config.get("tts", {}).get("provider", DEFAULT_TTS_PROVIDER)
    current_label = _TTS_PROVIDER_LABELS.get(current_provider, current_provider)
    print()
    _setup.print_header("Text-to-Speech Provider (optional)")
    _setup._info(f"Current: {current_label}", None)
    options = list(_TTS_PROVIDER_CHOICES)
    if tool_backend_helpers.managed_nous_tools_enabled() and nous_subscription.get_nous_subscription_features(config).nous_auth_present:
        options.insert(0, ("nous-openai",
                           "Nous Subscription (managed OpenAI TTS, billed to your subscription)"))
    choices = [label for _, label in options] + [f"Keep current ({current_label})"]
    keep_current_idx = len(choices) - 1
    idx = _setup.prompt_choice("Select TTS provider:", choices, keep_current_idx)
    if idx == keep_current_idx:
        return
    selected = options[idx][0]
    if selected == "nous-openai":
        selected = "openai"
        _setup.print_info("OpenAI TTS will use the managed Nous gateway and bill to your subscription.")
        if _setup.get_env_value("VOICE_TOOLS_OPENAI_KEY") or _setup.get_env_value("OPENAI_API_KEY"):
            _setup.print_warning("Direct OpenAI credentials are still configured and may take precedence "
                                 "until removed from ~/.hermes/.env.")
    elif selected in _TTS_LOCAL_PROVIDERS:
        selected = _tts_local_install_step(selected)
    else:
        selected = _tts_openai_key_step()
    config.setdefault("tts", {})["provider"] = selected
    _setup.save_config(config)
    _setup.print_success(f"TTS provider set to: {_TTS_PROVIDER_LABELS.get(selected, selected)}")


def setup_tts(config: dict):
    """Standalone TTS setup (for 'hermes setup tts')."""
    _setup_tts_provider(config)


import hermes_cli.setup as _setup
