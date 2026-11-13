"""A config still naming a removed TTS provider keeps working through the default provider."""

import json
import logging

from tools import tts_tool


def test_retired_provider_is_judged_by_the_default_requirements(monkeypatch):
    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"provider": "elevenlabs"})
    monkeypatch.setattr(tts_tool, "_plugin_provider_is_available", lambda name: False)
    monkeypatch.setitem(tts_tool._BUILTIN_REQUIREMENTS, "openai", lambda: True)
    assert tts_tool.check_tts_requirements() is True


def test_retired_provider_synthesizes_with_default_and_warns(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(tts_tool, "_load_tts_config", lambda: {"provider": "edge"})
    monkeypatch.setattr(tts_tool, "_dispatch_to_plugin_provider", lambda *a, **k: None)
    monkeypatch.setattr(tts_tool, "_importable", lambda importer: True)
    monkeypatch.setattr(tts_tool, "_once_warnings", set())

    def fake_openai(text, path, cfg, instructions=None):
        with open(path, "wb") as handle:
            handle.write(b"ID3" + b"\0" * 64)
        return path

    monkeypatch.setattr(tts_tool, "_generate_openai_tts", fake_openai)
    with caplog.at_level(logging.WARNING, logger="tools.tts_tool"):
        result = json.loads(tts_tool.text_to_speech_tool("Hello there.", output_path=str(tmp_path / "out.mp3")))

    assert result["success"] is True
    assert result["provider"] == "openai"
    assert "Unknown TTS provider 'edge'" in caplog.text
