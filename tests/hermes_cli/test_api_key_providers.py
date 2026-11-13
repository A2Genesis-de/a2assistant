"""Tests for API-key provider support."""

import json
import os

import pytest

from hermes_cli.auth import (
    PROVIDER_REGISTRY,
    resolve_provider,
    AuthError,
)


# =============================================================================
# Provider Registry tests
# =============================================================================


# =============================================================================
# Provider Resolution tests
# =============================================================================

# Derived from the live PROVIDER_REGISTRY so the list can never drift when a
# new provider (and its env var) is added — a hand-maintained tuple here was
# missing HF_TOKEN/DEEPINFRA_API_KEY, which made the auto-detection tests
# env-dependent (they failed on any machine with HF_TOKEN exported).
from hermes_cli.auth import PROVIDER_REGISTRY as _REGISTRY

_EXTRA_ENV_VARS = (
    # Checked directly in resolve_provider("auto"), not via the registry.
    "OPENROUTER_API_KEY", "NOUS_API_KEY",
    # Base URLs / paths that influence detection but aren't api_key_env_vars.
    "LM_BASE_URL", "KIMI_BASE_URL", "STEPFUN_BASE_URL", "KILOCODE_BASE_URL",
    "GMI_BASE_URL", "OPENAI_BASE_URL",
    "HERMES_COPILOT_ACP_COMMAND", "COPILOT_CLI_PATH",
    "HERMES_COPILOT_ACP_ARGS", "COPILOT_ACP_BASE_URL",
)

PROVIDER_ENV_VARS = tuple(
    dict.fromkeys(
        [var for cfg in _REGISTRY.values() for var in cfg.api_key_env_vars]
        + list(_EXTRA_ENV_VARS)
    )
)


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for key in PROVIDER_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("hermes_cli.auth._load_auth_store", dict)


class TestResolveProvider:
    """Test resolve_provider() with new providers."""


    def test_alias_chatgpt(self):
        """Issue #95794: ``--provider chatgpt`` selects the ChatGPT-backed Codex OAuth provider."""
        assert resolve_provider("chatgpt") == "openai-codex"
        assert resolve_provider("chatgpt-codex") == "openai-codex"

    def test_alias_chatgpt_every_alias_table(self):
        """Issue #95794: the runtime (providers.py), the /model parser (models_catalog_static via
        parse_model_input) and ``hermes auth login`` all resolve the ChatGPT alias, not just auth."""
        from hermes_cli.providers import normalize_provider
        from hermes_cli.models import parse_model_input
        from hermes_cli.auth_commands import _normalize_provider

        assert normalize_provider("chatgpt") == "openai-codex"
        assert normalize_provider("chatgpt-codex") == "openai-codex"
        assert parse_model_input("chatgpt:gpt-5.5", "openrouter") == ("openai-codex", "gpt-5.5")
        assert parse_model_input("chatgpt-codex:gpt-5.5", "openrouter") == ("openai-codex", "gpt-5.5")
        assert _normalize_provider("chatgpt") == "openai-codex"

    def test_unknown_provider_raises(self):
        with pytest.raises(AuthError):
            resolve_provider("nonexistent-provider-xyz")

    def test_openrouter_takes_priority_over_glm(self, monkeypatch):
        """OpenRouter API key should win over GLM in auto-detection."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        monkeypatch.setenv("GLM_API_KEY", "glm-key")
        assert resolve_provider("auto") == "openrouter"

    def test_auto_does_not_select_copilot_from_github_token(self, monkeypatch):
        # AWS Bedrock auto-detection (via boto3's credential chain) runs at
        # the tail of resolve_provider("auto") and will silently pick up
        # ~/.aws/credentials on developer machines that aren't blanked by
        # the hermetic conftest. Force-disable it so this test exercises
        # the specific "GitHub token alone shouldn't auto-pick copilot"
        # behavior, not the Bedrock fallback.
        monkeypatch.setattr(
            "agent.bedrock_adapter.has_aws_credentials",
            lambda env=None, **_kw: False,
        )
        monkeypatch.setenv("GITHUB_TOKEN", "gh-test-token")
        with pytest.raises(AuthError, match="not connected to any AI provider"):
            resolve_provider("auto")


# =============================================================================
# API Key Provider Status tests
# =============================================================================

# =============================================================================
# Credential Resolution tests
# =============================================================================

# =============================================================================
# Runtime Provider Resolution tests
# =============================================================================

class TestRuntimeProviderResolution:

    def test_runtime_external_process_provider_uses_process_runtime(self, monkeypatch, tmp_path):
        import providers
        from hermes_cli import auth
        from providers.base import ProviderProfile

        profile = ProviderProfile(name="acme-acp", auth_type="external_process", base_url="acp://acme",
                                  process_command="acme", process_args=("--acp", "--stdio"),
                                  process_args_env_var="HERMES_ACME_ACP_ARGS")
        monkeypatch.setitem(providers._REGISTRY, profile.name, profile)
        monkeypatch.setattr(providers, "_PROVIDER_LIST_CACHE", None)
        monkeypatch.setattr(auth, "PROVIDER_REGISTRY", dict(auth.PROVIDER_REGISTRY))
        auth.PROVIDER_REGISTRY[profile.name] = auth.ProviderConfig(
            profile.name, profile.name, profile.auth_type, inference_base_url=profile.base_url)
        cli = tmp_path / ("acme.exe" if os.name == "nt" else "acme")
        cli.write_text("", encoding="utf-8")
        cli.chmod(0o755)
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setenv("HERMES_ACME_ACP_ARGS", "--acp --stdio --debug")

        from hermes_cli.runtime_provider import resolve_runtime_provider

        result = resolve_runtime_provider(requested="acme-acp")

        assert result["provider"] == "acme-acp"
        assert result["api_mode"] == "chat_completions"
        assert result["api_key"] == "acme-acp"
        assert result["base_url"] == "acp://acme"
        assert os.path.samefile(result["command"], cli)
        assert result["args"] == ["--acp", "--stdio", "--debug"]


# =============================================================================
# _has_any_provider_configured tests
# =============================================================================

class TestHasAnyProviderConfigured:


    def test_claude_code_creds_ignored_on_fresh_install(self, monkeypatch, tmp_path):
        """Claude Code credentials should NOT skip the wizard when Hermes is unconfigured."""
        from hermes_cli import config as config_module
        hermes_home = tmp_path / ".hermes"
        hermes_home.mkdir()
        monkeypatch.setattr(config_module, "get_env_path", lambda: hermes_home / ".env")
        monkeypatch.setattr(config_module, "get_hermes_home", lambda: hermes_home)
        # Clear all provider env vars so earlier checks don't short-circuit
        _all_vars = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                      "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"}
        for pconfig in PROVIDER_REGISTRY.values():
            if pconfig.auth_type == "api_key":
                _all_vars.update(pconfig.api_key_env_vars)
        for var in _all_vars:
            monkeypatch.delenv(var, raising=False)
        # Prevent gh-cli / copilot auth fallback from leaking in
        monkeypatch.setattr("hermes_cli.auth.get_auth_status", lambda _pid: {})
        # Simulate valid Claude Code credentials
        monkeypatch.setattr(
            "agent.anthropic_credentials.read_claude_code_credentials",
            lambda: {"accessToken": "sk-ant-test", "refreshToken": "ref-tok"},
        )
        monkeypatch.setattr(
            "agent.anthropic_credentials.is_claude_code_token_valid",
            lambda creds: True,
        )
        from hermes_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is False

    def test_config_provider_counts(self, monkeypatch, tmp_path):
        """config.yaml with model.provider set should count as configured."""
        import hermes_yaml as yaml
        from hermes_cli import config as config_module
        hermes_home = tmp_path / ".hermes"
        hermes_home.mkdir()
        config_file = hermes_home / "config.yaml"
        config_file.write_text(yaml.safe_dump({
            "model": {"default": "anthropic/claude-opus-4.6", "provider": "openrouter"},
        }))
        monkeypatch.setattr(config_module, "get_env_path", lambda: hermes_home / ".env")
        monkeypatch.setattr(config_module, "get_hermes_home", lambda: hermes_home)
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        # Clear all provider env vars
        for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                     "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"):
            monkeypatch.delenv(var, raising=False)
        from hermes_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True

    @staticmethod
    def _clear_provider_env(monkeypatch):
        """Clear every provider env var so early checks can't short-circuit."""
        _all_vars = {"OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                     "ANTHROPIC_TOKEN", "OPENAI_BASE_URL"}
        for pconfig in PROVIDER_REGISTRY.values():
            if pconfig.auth_type == "api_key":
                _all_vars.update(pconfig.api_key_env_vars)
        for var in _all_vars:
            monkeypatch.delenv(var, raising=False)

    def _setup_home(self, monkeypatch, tmp_path):
        from hermes_cli import config as config_module
        hermes_home = tmp_path / ".hermes"
        hermes_home.mkdir()
        monkeypatch.setattr(config_module, "get_env_path", lambda: hermes_home / ".env")
        monkeypatch.setattr(config_module, "get_hermes_home", lambda: hermes_home)
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        self._clear_provider_env(monkeypatch)
        return hermes_home

    def test_config_provider_skips_registry_sweep(self, monkeypatch, tmp_path):
        """model.provider in config.yaml must short-circuit BEFORE the slow
        provider-registry sweep (gh subprocess etc.) is ever invoked.

        Regression test for the auth-first ordering: get_auth_status is
        booby-trapped to fail loudly if the sweep runs. The sweep wraps its
        loop in ``except Exception``, so we also record every call — any
        recorded call proves the sweep ran even if the raise was swallowed.
        """
        import hermes_yaml as yaml
        hermes_home = self._setup_home(monkeypatch, tmp_path)
        (hermes_home / "config.yaml").write_text(yaml.safe_dump({
            "model": {"default": "anthropic/claude-opus-4.6", "provider": "openrouter"},
        }))
        sweep_calls = []

        def _trap(provider_id):
            sweep_calls.append(provider_id)
            raise AssertionError("sweep must be skipped")

        monkeypatch.setattr("hermes_cli.auth.get_auth_status", _trap)
        from hermes_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert sweep_calls == [], (
            f"provider registry sweep ran before config short-circuit: {sweep_calls}"
        )

    def test_config_base_url_api_key_skips_registry_sweep(self, monkeypatch, tmp_path):
        """Custom endpoint (base_url/api_key in config, no provider) must also
        short-circuit before the registry sweep."""
        import hermes_yaml as yaml
        hermes_home = self._setup_home(monkeypatch, tmp_path)
        (hermes_home / "config.yaml").write_text(yaml.safe_dump({
            "model": {
                "default": "local/custom-model",
                "base_url": "http://localhost:8000/v1",
                "api_key": "sk-local-test",
            },
        }))
        sweep_calls = []

        def _trap(provider_id):
            sweep_calls.append(provider_id)
            raise AssertionError("sweep must be skipped")

        monkeypatch.setattr("hermes_cli.auth.get_auth_status", _trap)
        from hermes_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert sweep_calls == [], (
            f"provider registry sweep ran before config short-circuit: {sweep_calls}"
        )

    def test_auth_json_skips_registry_sweep(self, monkeypatch, tmp_path):
        """auth.json with a logged-in active provider must short-circuit before
        the registry sweep. get_auth_status may be called ONLY for the active
        provider from auth.json — any other provider id means the sweep ran.
        """
        hermes_home = self._setup_home(monkeypatch, tmp_path)
        (hermes_home / "auth.json").write_text(json.dumps({
            "active_provider": "nous",
        }))
        calls = []

        def _guarded_status(provider_id):
            calls.append(provider_id)
            assert provider_id == "nous", "sweep must be skipped"
            return {"logged_in": True}

        monkeypatch.setattr("hermes_cli.auth.get_auth_status", _guarded_status)
        from hermes_cli.main import _has_any_provider_configured
        assert _has_any_provider_configured() is True
        assert calls == ["nous"], (
            f"provider registry sweep ran before auth.json short-circuit: {calls}"
        )


# =============================================================================
# Kimi Code auto-detection tests
# =============================================================================

MOONSHOT_DEFAULT_URL = "https://api.moonshot.ai/v1"


# =============================================================================
# Kimi / Moonshot model list isolation tests
# =============================================================================

# =============================================================================
# Hugging Face provider model list tests
# =============================================================================

# =============================================================================
# NovitaAI provider tests (added by feat/add-novita-provider)
# =============================================================================

# =============================================================================
# MiniMax OAuth provider tests (added by feat/minimax-oauth-provider)
# =============================================================================

# =============================================================================
# DeepInfra provider tests
# =============================================================================
# Registration / alias / env-var invariants are asserted in
# TestProviderRegistry + TestResolveProvider above. The classes below
# cover the catalog/tag/pricing/profile machinery added on top of the
# baseline provider wiring.


@pytest.fixture
def _deepinfra_cache_isolation(monkeypatch):
    """Reset the module-level catalog cache around each DeepInfra test.

    The cache is keyed by base URL and would otherwise leak fixture data
    from one test into the next in the same session. The negative cache is
    reset too, so a test that simulates an unreachable catalog can't suppress
    a later test's fetch within the failure TTL.
    """
    import hermes_cli.models as _models_mod
    monkeypatch.setattr(_models_mod, "_deepinfra_catalog_cache", {})
    monkeypatch.setattr(_models_mod, "_deepinfra_catalog_neg_cache", {})
    yield


def _make_urlopen_returning(payload):
    """Helper: build a urlopen() shim returning a fixed JSON payload."""
    import json as _json

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps(payload).encode()

    return lambda *a, **kw: _Resp()


@pytest.mark.usefixtures("_deepinfra_cache_isolation")
class TestDeepInfraTagFiltering:
    """Contract tests for the shared _fetch_deepinfra_models_by_tag helper."""

    def test_filters_by_surface_tag_and_handles_rollout_states(self, monkeypatch):
        # One payload, several invariants in one test:
        #  - explicit surface tags are honored (chat / image-gen / tts / stt / embed)
        #  - capability-tags-only items fall through to the regex fallback
        #    (used during the surface-tag rollout)
        #  - the regex excludes id-name matches (whisper, embed, …)
        #  - a surface tag takes priority over the regex
        #  - ``metadata: None`` stubs are dropped
        payload = {"data": [
            {"id": "vendor/chat-tagged", "metadata": {"tags": ["chat"]}},
            {"id": "vendor/image-tagged", "metadata": {"tags": ["image-gen"]}},
            {"id": "vendor/tts-tagged", "metadata": {"tags": ["tts"]}},
            {"id": "vendor/stt-tagged", "metadata": {"tags": ["stt"]}},
            {"id": "vendor/embed-tagged", "metadata": {"tags": ["embed"]}},
            # capability-only — rolls through regex fallback
            {"id": "Qwen/Qwen3-30B", "metadata": {"tags": ["reasoning", "vision"]}},
            {"id": "openai/whisper-large", "metadata": {"tags": ["reasoning"]}},
            # surface tag overrides legacy regex exclusion
            {"id": "some-org/whisper-finetune-chat", "metadata": {"tags": ["chat"]}},
            # null metadata — stub model, must be skipped
            {"id": "stub-model", "metadata": None},
        ]}
        from hermes_cli.models import _fetch_deepinfra_models_by_tag
        import hermes_cli.models as _m

        for surface in ("chat", "image-gen", "tts", "stt", "embed"):
            monkeypatch.setattr(
                _m,
                "_urlopen_model_catalog_request",
                _make_urlopen_returning(payload),
            )
            # Reset cache between iterations so each surface re-parses the payload.
            _m._deepinfra_catalog_cache.clear()
            got = _fetch_deepinfra_models_by_tag(surface)
            assert got is not None
            ids = {item["id"] for item in got}
            assert "stub-model" not in ids  # null-metadata always skipped
            if surface == "chat":
                # explicit chat + capability-only (Qwen) + surface-tag-over-regex
                assert "vendor/chat-tagged" in ids
                assert "Qwen/Qwen3-30B" in ids
                assert "some-org/whisper-finetune-chat" in ids
                # regex still excludes capability-only items that match the excluder
                assert "openai/whisper-large" not in ids
            else:
                # non-chat surfaces only see explicit surface-tagged items
                for item in got:
                    assert surface in item["metadata"]["tags"]


@pytest.fixture
def _kilo_pricing_isolation(monkeypatch):
    """Reset the shared pricing caches around each Kilo pricing test.

    The Kilo fetcher keys the shared pricing cache by its catalog URL; without
    a reset, one test's payload (or its negative cache entry) would answer
    the next test's read.
    """
    import hermes_cli.models_pricing as _mp
    monkeypatch.setattr(_mp, "_pricing_cache", {})
    monkeypatch.setattr(_mp, "_pricing_cache_retry_after", {})
    monkeypatch.setattr(_mp, "_pricing_provider_cache_keys", {})

