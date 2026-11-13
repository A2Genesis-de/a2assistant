"""Tests for the unified STT language resolution (_resolve_stt_language).

Class-level contract: EVERY provider resolves its language hint through one
helper with the order:

    stt.<provider>.language > stt.language (global) > HERMES_LOCAL_STT_LANGUAGE > None

Regression coverage for the "STT transcribes the wrong language" issue class
(#55551, #50181 and siblings):
  - the global ``stt.language`` key reaches every provider
  - per-provider language still wins over the global key
"""

import pytest

from tools.transcription_tools import _resolve_stt_language


@pytest.fixture(autouse=True)
def _clear_lang_env(monkeypatch):
    monkeypatch.delenv("HERMES_LOCAL_STT_LANGUAGE", raising=False)


class TestResolveSttLanguage:
    def test_provider_language_wins(self):
        cfg = {"language": "en", "openai": {"language": "he"}}
        assert _resolve_stt_language("openai", cfg) == "he"

    def test_global_language_fallback(self):
        cfg = {"language": "hu", "openai": {}}
        assert _resolve_stt_language("openai", cfg) == "hu"


    def test_value_is_stripped(self):
        cfg = {"language": " ja "}
        assert _resolve_stt_language("local", cfg) == "ja"
