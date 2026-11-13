"""Tests for setup.py configuration flows."""
import sys

import pytest


from hermes_cli.config import load_config, save_config
import hermes_cli.main  # bootstrap before per-test filesystem guards
from hermes_cli import setup as setup_mod
from hermes_cli.setup import setup_model_provider


def _maybe_keep_current_tts(question, choices):
    if question != "Select TTS provider:":
        return None
    assert choices[-1].startswith("Keep current (")
    return len(choices) - 1


def _clear_provider_env(monkeypatch):
    for key in (
        "NOUS_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_tts(monkeypatch):
    """Stub out TTS prompts so setup_model_provider doesn't block."""
    monkeypatch.setattr("hermes_cli.setup.prompt_choice", lambda q, c, d=0: (
        _maybe_keep_current_tts(q, c) if _maybe_keep_current_tts(q, c) is not None
        else d
    ))
    monkeypatch.setattr("hermes_cli.setup.prompt_yes_no", lambda *a, **kw: False)


def _write_model_config(tmp_path, provider, base_url="", model_name="test-model"):
    """Simulate what a _model_flow_* function writes to disk."""
    cfg = load_config()
    m = cfg.get("model")
    if not isinstance(m, dict):
        m = {"default": m} if m else {}
        cfg["model"] = m
    m["provider"] = provider
    if base_url:
        m["base_url"] = base_url
    if model_name:
        m["default"] = model_name
    save_config(cfg)


def test_setup_delegates_to_select_provider_and_model(tmp_path, monkeypatch):
    """setup_model_provider calls select_provider_and_model and syncs config."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    config = load_config()

    def fake_select():
        _write_model_config(tmp_path, "custom", "http://localhost:11434/v1", "qwen3.5:32b")

    monkeypatch.setattr("hermes_cli.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "custom"
    assert reloaded["model"]["base_url"] == "http://localhost:11434/v1"
    assert reloaded["model"]["default"] == "qwen3.5:32b"


def test_select_provider_and_model_warns_if_named_custom_provider_disappears(
    tmp_path, monkeypatch, capsys
):
    """If a saved custom provider is deleted mid-selection, show a warning instead of silently doing nothing."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    cfg = load_config()
    cfg["custom_providers"] = [{"name": "Local", "base_url": "http://localhost:8080/v1"}]
    save_config(cfg)

    def fake_prompt_provider_choice(choices, default=0):
        current = load_config()
        current["custom_providers"] = []
        save_config(current)
        return next(i for i, label in enumerate(choices) if label.startswith("Local (localhost:8080/v1)"))

    monkeypatch.setattr("hermes_cli.auth.resolve_provider", lambda provider: None)
    monkeypatch.setattr("hermes_cli.main._prompt_provider_choice", fake_prompt_provider_choice)
    monkeypatch.setattr(
        "hermes_cli.main._model_flow_named_custom",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("named custom flow should not run")),
    )

    from hermes_cli.main import select_provider_and_model

    select_provider_and_model()

    out = capsys.readouterr().out
    assert "selected saved custom provider is no longer available" in out


# test_setup_slack_* moved to tests/gateway/test_slack_plugin_setup.py — the
# _setup_slack wizard migrated to the slack plugin's interactive_setup (#41112).


@pytest.mark.parametrize("extra", ["kittentts"])
@pytest.mark.parametrize("succeeds", [True, False])
def test_python_setup_uses_declared_extras_and_reports_restart(extra, succeeds, monkeypatch, capsys):
    import pm
    from hermes_cli import setup_tts

    calls = []
    def sync(extras, *, explicit):
        calls.append((extras, explicit))
        if not succeeds:
            raise pm.InstallError("venv", "resolution refused")

    monkeypatch.setattr(pm, "sync_venv", sync)
    monkeypatch.setattr("pm.extras.extra_supported", lambda name: True)
    monkeypatch.setitem(sys.modules, extra, None)
    assert setup_tts._install_kittentts_deps() is succeeds
    assert calls == [([extra], True)]
    output = capsys.readouterr().out
    if succeeds:
        assert "Restart A2Assistant" in output
        assert sys.modules[extra] is None  # installing never activates in this process
    else:
        assert "resolution refused" in output
        assert "Retry with: hermes setup" in output
        assert "installed." not in output


@pytest.mark.parametrize("extra", ["kittentts"])
def test_unsupported_tts_selection_is_retained_without_installing(extra, monkeypatch, capsys):
    from hermes_cli import setup_tts

    monkeypatch.setattr("pm.extras.extra_supported", lambda name: False)
    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported engine must not install system or Python packages")
    monkeypatch.setattr(setup_mod, "prompt_yes_no", forbidden)
    monkeypatch.setattr("pm.sync_venv", forbidden)
    assert setup_tts._tts_local_install_step(extra) == extra
    output = capsys.readouterr().out
    assert "not supported" in output and "selection is saved" in output
