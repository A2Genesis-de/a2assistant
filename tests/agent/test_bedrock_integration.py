"""Integration tests for the AWS Bedrock provider wiring.

Verifies that the Bedrock provider is correctly registered in the
provider registry, model catalog, and runtime resolution pipeline.
These tests do NOT require AWS credentials or boto3 — all AWS calls
are mocked.

Note: Tests that import ``hermes_cli.auth`` or ``hermes_cli.runtime_provider``
require Python 3.10+ due to ``str | None`` type syntax in the import chain.
"""


import pytest


_BOTO_PREFIXES = ("botocore", "boto3")


@pytest.fixture(autouse=True)
def _boto_sys_modules_hygiene():
    """Snapshot/restore boto* sys.modules around every test.

    Tests here plant fake botocore/boto3 modules; a fake that leaks (or a
    real submodule first-imported inside a stub window) poisons later
    imports of the real ``botocore.exceptions`` with
    ``No module named 'botocore.vendored'`` (PR #92617 CI flake). This
    fixture makes stub windows airtight regardless of test ordering.
    """
    import sys as _sys

    saved = {
        name: mod
        for name, mod in _sys.modules.items()
        if name.split(".", 1)[0] in _BOTO_PREFIXES
    }
    yield
    for name in [n for n in _sys.modules if n.split(".", 1)[0] in _BOTO_PREFIXES]:
        _sys.modules.pop(name, None)
    _sys.modules.update(saved)













class TestRuntimeProvider:
    """Verify resolve_runtime_provider() handles bedrock correctly."""



    def test_bedrock_openai_models_do_not_fall_back_to_default_context(self):
        """The Mantle OpenAI models have a larger window than the generic
        default; make sure they never fall back to it."""
        from agent.bedrock_adapter import (
            BEDROCK_DEFAULT_CONTEXT_LENGTH,
            BEDROCK_OPENAI_RESPONSES_MODEL_IDS,
            get_bedrock_context_length,
        )
        for model_id in BEDROCK_OPENAI_RESPONSES_MODEL_IDS:
            assert get_bedrock_context_length(model_id) > BEDROCK_DEFAULT_CONTEXT_LENGTH, model_id


# ---------------------------------------------------------------------------
# providers.py integration
# ---------------------------------------------------------------------------

class TestProvidersModule:
    """Verify bedrock is wired into hermes_cli/providers.py."""



    def test_determine_api_mode_from_bedrock_url(self):
        from hermes_cli.providers import determine_api_mode
        assert determine_api_mode(
            "unknown", "https://bedrock-runtime.us-east-1.amazonaws.com"
        ) == "bedrock_converse"



# ---------------------------------------------------------------------------
# Error classifier integration
# ---------------------------------------------------------------------------

class TestErrorClassifierBedrock:
    """Verify Bedrock error patterns are in the global error classifier."""

    def test_bedrock_throttling_classified_as_rate_limit(self):
        from agent.error_classifier import FailoverReason, classify_api_error
        err = Exception(
            "An error occurred (ThrottlingException) when calling the ConverseStream "
            "operation: Too many requests, please wait before trying again."
        )
        assert classify_api_error(err, provider="bedrock").reason == FailoverReason.rate_limit

    def test_bedrock_input_too_long_classified_as_context_overflow(self):
        from agent.error_classifier import FailoverReason, classify_api_error
        err = Exception(
            "An error occurred (ValidationException) when calling the ConverseStream "
            "operation: Input is too long for requested model."
        )
        assert classify_api_error(err, provider="bedrock").reason == FailoverReason.context_overflow


# ---------------------------------------------------------------------------
# pyproject.toml bedrock extra
# ---------------------------------------------------------------------------

class TestPackaging:
    """Verify Bedrock remains a declared lazy optional dependency."""

    @staticmethod
    def _optional_dependencies():
        import tomllib
        from pathlib import Path

        content = (Path(__file__).parent.parent.parent / "pyproject.toml").read_text()
        return tomllib.loads(content)["project"]["optional-dependencies"]

    def test_bedrock_extra_exists(self):
        extras = self._optional_dependencies()
        assert "bedrock" in extras
        assert any(dep.startswith("boto3==") for dep in extras["bedrock"])

    def test_bedrock_is_not_eager_installed_by_all_extra(self):
        extras = self._optional_dependencies()
        assert "hermes-agent[bedrock]" not in extras["all"]


# ---------------------------------------------------------------------------
# Model ID dot preservation — regression for #11976
# ---------------------------------------------------------------------------
# AWS Bedrock inference-profile model IDs embed structural dots:
#
#   global.anthropic.claude-opus-4-7
#   us.anthropic.claude-sonnet-4-5-20250929-v1:0
#   apac.anthropic.claude-haiku-4-5
#
# ``agent.anthropic_message_convert.normalize_model_name`` converts dots to hyphens
# unless the caller opts in via ``preserve_dots=True``.  Before this fix,
# ``AIAgent._anthropic_preserve_dots`` returned False for the ``bedrock``
# provider, so Claude-on-Bedrock requests went out with
# ``global-anthropic-claude-opus-4-7`` (all dots mangled to hyphens) and
# Bedrock rejected them with:
#
#   HTTP 400: The provided model identifier is invalid.
#
# The fix adds ``bedrock`` to the preserve-dots provider allowlist and
# ``bedrock-runtime.`` to the base-URL heuristic, mirroring the shape of
# the opencode-go fix for #5211 (commit f77be22c), which extended this
# same allowlist.


class TestBedrockPreserveDotsFlag:
    """``AIAgent._anthropic_preserve_dots`` must return True on Bedrock so
    inference-profile IDs survive the normalize step intact."""

    def test_bedrock_provider_preserves_dots(self):
        from types import SimpleNamespace
        agent = SimpleNamespace(provider="bedrock", base_url="")
        from run_agent import AIAgent
        assert AIAgent._anthropic_preserve_dots(agent) is True



    def test_non_bedrock_aws_url_does_not_preserve_dots(self):
        """Unrelated AWS endpoints (e.g. ``s3.us-east-1.amazonaws.com``)
        must not accidentally activate the dot-preservation heuristic —
        the heuristic is scoped to the ``bedrock-runtime.`` substring
        specifically."""
        from types import SimpleNamespace
        agent = SimpleNamespace(
            provider="custom",
            base_url="https://s3.us-east-1.amazonaws.com",
        )
        from run_agent import AIAgent
        assert AIAgent._anthropic_preserve_dots(agent) is False



class TestBedrockModelNameNormalization:
    """End-to-end: ``normalize_model_name`` + the preserve-dots flag
    reproduce the exact production request shape for each Bedrock model
    family, confirming the fix resolves the reporter's HTTP 400."""




    def test_bedrock_prefix_preserved_without_preserve_dots(self):
        """Bedrock inference profile IDs are auto-detected by prefix and
        always returned unmangled -- ``preserve_dots`` is irrelevant for
        these IDs because the dots are namespace separators, not version
        separators.  Regression for #12295."""
        from agent.anthropic_message_convert import normalize_model_name
        assert normalize_model_name(
            "global.anthropic.claude-opus-4-7", preserve_dots=False
        ) == "global.anthropic.claude-opus-4-7"



class TestBedrockBuildAnthropicKwargsEndToEnd:
    """Integration: calling ``build_anthropic_kwargs`` with a Bedrock-
    shaped model ID and ``preserve_dots=True`` produces the unmangled
    model string in the outgoing kwargs — the exact body sent to the
    ``bedrock-runtime.`` endpoint.  This is the integration-level
    regression for the reporter's HTTP 400."""


    def test_bedrock_model_preserved_without_preserve_dots(self):
        """Bedrock inference profile IDs survive ``build_anthropic_kwargs``
        even without ``preserve_dots=True`` -- the prefix auto-detection
        in ``normalize_model_name`` is the load-bearing piece.
        Regression for #12295."""
        from agent.anthropic_adapter import build_anthropic_kwargs
        kwargs = build_anthropic_kwargs(
            model="global.anthropic.claude-opus-4-7",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            max_tokens=1024,
            reasoning_config=None,
            preserve_dots=False,
        )
        assert kwargs["model"] == "global.anthropic.claude-opus-4-7"


class TestBedrockModelIdDetection:
    """Tests for ``_is_bedrock_model_id`` and the auto-detection that
    makes ``normalize_model_name`` preserve dots for Bedrock IDs
    regardless of ``preserve_dots``.  Regression for #12295."""







    def test_bare_bedrock_id_preserved_without_flag(self):
        """The primary bug from #12295: ``anthropic.claude-opus-4-7``
        sent to bedrock-mantle via auxiliary clients that don't pass
        ``preserve_dots=True``."""
        from agent.anthropic_message_convert import normalize_model_name
        assert normalize_model_name(
            "anthropic.claude-opus-4-7", preserve_dots=False
        ) == "anthropic.claude-opus-4-7"




# ---------------------------------------------------------------------------
# auxiliary_client Bedrock resolution — fix for #13919
# ---------------------------------------------------------------------------
# Before the fix, resolve_provider_client("bedrock", ...) fell through to the
# "unhandled auth_type" warning and returned (None, None), breaking all
# auxiliary tasks (compression, memory, summarization) for Bedrock users.

