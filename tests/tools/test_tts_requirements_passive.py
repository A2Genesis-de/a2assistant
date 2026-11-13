"""``check_tts_requirements`` is the ``text_to_speech`` tool's ``check_fn``: a PASSIVE probe.

A tool listing runs it every turn and on boot, so it must answer from what is installed and
configured and never start a dependency install.
"""

import pytest

from tools import tts_tool


@pytest.fixture
def installs(monkeypatch):
    """Records any install a requirement check attempts, and fails loudly on one."""
    import pm

    calls: list[str] = []

    def fake_ensure(extra):
        calls.append(extra)
        raise AssertionError(f"a TTS requirement check installed {extra!r}")

    monkeypatch.setattr(pm, "ensure_import", fake_ensure)
    return calls


@pytest.mark.parametrize("provider", ["openai", "kittentts", "piper"])
def test_missing_engine_reports_unavailable_without_installing(monkeypatch, installs, provider):
    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"provider": provider})
    monkeypatch.setattr(tts_tool, "_package_installed", lambda name: False)
    monkeypatch.setattr(tts_tool, "_check_kittentts_available", lambda: False)
    monkeypatch.setattr(tts_tool, "_check_piper_available", lambda: False)
    assert tts_tool.check_tts_requirements() is False
    assert installs == []
