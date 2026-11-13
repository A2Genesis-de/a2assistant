"""Golden wire snapshot, widened: per-model variants, stream-time kwargs and auxiliary requests.

``test_provider_wire_snapshot`` records one model per provider at unset/high/off reasoning. Many
request quirks are gated on the model id (DeepSeek V3 vs V4, GLM 4.x / 5.2 / 5.3, Solar, MiniMax
M3 on the OpenAI host), on the requested effort (clamp
ladders and overrides: ``minimal``, ``low``, ``xhigh``, effort ``none``) or on an explicit
``max_tokens`` (``max_tokens`` vs ``max_completion_tokens``); each such branch gets one variant
cell here, recorded over the wider REASONING_LADDER. Two request surfaces the base snapshot never
reaches are recorded too:

- ``stream:*`` — what the streaming request path adds on top of the built request, as a delta:
  ``_StreamingCall._call_chat_completions`` (socket ``timeout``, llama-server ``return_progress``)
  through ``_open_chat_stream`` (``stream``, ``stream_options``), captured at
  ``client.chat.completions.create``.
- ``aux:*`` — the auxiliary client's final chat kwargs (``auxiliary_client._build_call_kwargs``)
  per provider x reasoning setting, including the max_tokens forwarding / key choice and the
  caller- and task-level ``extra_body.reasoning`` merge.

Cells live in ``tests/fixtures/provider_wire_snapshot_variants.json``; regenerate and review the
diff exactly like the base snapshot::

    HERMES_UPDATE_WIRE_SNAPSHOT=1 .venv/bin/python -m pytest tests/agent/transports/test_provider_wire_snapshot_variants.py
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.agent.transports import test_provider_wire_snapshot as base

SNAPSHOT = Path(__file__).resolve().parents[2] / "fixtures" / "provider_wire_snapshot_variants.json"
offline = base.offline

# The base rows plus the efforts clamp ladders and overrides treat specially. Effort ``none`` with
# thinking enabled is a real request shape (voice turns), distinct from ``enabled: False``.
REASONING_LADDER: dict[str, Any] = {
    **base.REASONING,
    "minimal": {"enabled": True, "effort": "minimal"},
    "low": {"enabled": True, "effort": "low"},
    "xhigh": {"enabled": True, "effort": "xhigh"},
    "none": {"enabled": True, "effort": "none"},
}

# (key, provider, model, base_url, AIAgent kwargs). Each cell reaches a branch the base cell for
# that provider does not; the comment names it.
MODEL_VARIANTS: list[tuple[str, str, str, str, dict[str, Any]]] = [
    # Explicit max_tokens for gpt-5.5 behind OpenRouter: Responses route, max_output_tokens.
    ("variant:openrouter-gpt-5.5-max-tokens", "openrouter", "openai/gpt-5.5", "https://openrouter.ai/api/v1",
     {"max_tokens": 4096}),
    # Explicit max_tokens for an OpenAI chat model behind OpenRouter: model-name fallback to
    # max_completion_tokens (model_forces_max_completion_tokens).
    ("variant:openrouter-gpt-4.1-max-tokens", "openrouter", "openai/gpt-4.1", "https://openrouter.ai/api/v1",
     {"max_tokens": 4096}),
    # Explicit max_tokens on a generic endpoint -> plain max_tokens.
    ("variant:custom-max-tokens", "custom", "my-local-model", "http://127.0.0.1:8080/v1", {"max_tokens": 4096}),
]

# (key, provider, model, base_url, agent attributes set after construction).
STREAM_CELLS: list[tuple[str, str, str, str, dict[str, Any]]] = [
    ("stream:openrouter", "openrouter", "anthropic/claude-opus-5.5", "https://openrouter.ai/api/v1", {}),
    # Local endpoint: the stream read timeout is raised to the base timeout.
    ("stream:custom", "custom", "my-local-model", "http://127.0.0.1:8080/v1", {}),
    # llama-server: prompt-progress chunks requested (with_prompt_progress) on every stream.
    ("stream:llamacpp", "llamacpp", "qwen3-8b", "http://127.0.0.1:8080/v1", {}),
    # An endpoint that already rejected stream_options this session.
    ("stream:custom-stream-options-rejected", "custom", "my-local-model", "http://127.0.0.1:8080/v1",
     {"_stream_options_unsupported": True}),
]

# (key, provider, model, base_url, options) for the auxiliary client. Options: ``config`` (YAML
# written to the test's HERMES_HOME config.yaml), ``task``, ``extra_body``.
AUX_CELLS: list[tuple[str, str, str, str | None, dict[str, Any]]] = [
    ("aux:openrouter", "openrouter", "anthropic/claude-opus-5.5", "https://openrouter.ai/api/v1", {}),
    # OpenRouter forwards max_tokens; an OpenAI-family model name turns it into max_completion_tokens.
    ("aux:openrouter-gpt-5.5", "openrouter", "openai/gpt-5.5", "https://openrouter.ai/api/v1", {}),
    ("aux:nous", "nous", "anthropic/claude-opus-5.5", "https://inference-api.nousresearch.com/v1", {}),
    ("aux:custom", "custom", "my-local-model", "http://127.0.0.1:8080/v1", {}),
    # No profile (base_url-only caller): the generic extra_body.reasoning fallback.
    ("aux:no-profile", "", "my-model", "https://llm.example.com/v1", {}),
    # Configured main endpoint is api.openai.com, no OpenRouter key, no Nous auth: a forwarded
    # max_tokens (MoA reference slot) becomes max_completion_tokens for a non-OpenAI model name.
    ("aux:custom-direct-openai-moa", "custom", "my-model", None, {
        "task": "moa_reference",
        "config": "model:\n  provider: custom\n  base_url: https://api.openai.com/v1\n  default: my-model\n"}),
    # Caller extra_body.reasoning without ``enabled``: kept beside the profile's reasoning_effort
    # (clamped by _merge_aux_extra_body: ``ultra`` -> ``max``), dropped when the call turns
    # reasoning off.
    ("aux:custom-caller-reasoning", "custom", "my-local-model", "http://127.0.0.1:8080/v1", {
        "extra_body": {"reasoning": {"effort": "ultra"}}}),
    # auxiliary.<task>.reasoning_effort folded by _get_task_extra_body into the request reasoning.
    ("aux:custom-task-reasoning", "custom", "my-local-model", "http://127.0.0.1:8080/v1", {
        "task": "compression", "config": "auxiliary:\n  compression:\n    reasoning_effort: low\n"}),
    # auxiliary.<task>.reasoning_effort: ultra becomes the call's reasoning_config; the entry clamp
    # in _build_call_kwargs is what keeps ``ultra`` off this profile's wire (custom clamps itself).
    ("aux:openrouter-task-ultra", "openrouter", "anthropic/claude-opus-5.5", "https://openrouter.ai/api/v1", {
        "task": "compression", "config": "auxiliary:\n  compression:\n    reasoning_effort: ultra\n"}),
]

CELL_KEYS = frozenset(c[0] for cells in (MODEL_VARIANTS, STREAM_CELLS, AUX_CELLS) for c in cells)


class _Sent(Exception):
    """Raised by the fake client once the streaming request is captured."""


def _stream_delta(provider: str, model: str, base_url: str, attrs: dict[str, Any]) -> dict[str, Any]:
    """Keys the streaming request path adds to or changes in the built request, for one
    chat-completions agent: ``_call_chat_completions`` runs until ``chat.completions.create``."""
    from agent.chat_completion_helpers import _StreamingCall

    agent = base._agent(provider, model, base_url)
    for name, value in attrs.items():
        setattr(agent, name, value)
    assert agent.api_mode == "chat_completions", f"{provider}/{model} no longer streams over chat completions"
    built = base._request(agent, None)
    sent: dict[str, Any] = {}

    def create(**kwargs):
        sent.update(kwargs)
        raise _Sent

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    agent._create_request_openai_client = lambda **_kwargs: client
    call = _StreamingCall(agent, copy.deepcopy(built), None)
    with pytest.raises(_Sent):
        call._call_chat_completions(call.stream_attempt_state["current"])
    added = {k: v for k, v in sent.items() if k not in built or built[k] != v}
    return base._scrub({"api_mode": agent.api_mode, "added": added, "removed": sorted(set(built) - set(sent))})


def _aux_kwargs(monkeypatch, provider: str, model: str, base_url: str | None, opts: dict[str, Any]) -> dict[str, Any]:
    """``_build_call_kwargs`` per reasoning setting, with temperature, max_tokens and tools set."""
    from agent import auxiliary_client as aux

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # flips the direct-OpenAI key choice
    if "config" in opts:
        Path(os.environ["HERMES_HOME"], "config.yaml").write_text(opts["config"], encoding="utf-8")
    task = opts.get("task")
    main = {"provider": provider, "model": model, "base_url": base_url or "", "session_id": "aux-snapshot"}
    out: dict[str, Any] = {}
    with aux.scoped_runtime_main(main):
        for label, reasoning in base.REASONING.items():
            messages = json.loads(json.dumps(base.MESSAGES))
            extra_body = json.loads(json.dumps(opts.get("extra_body"))) if "extra_body" in opts else None
            if task and extra_body is None:
                extra_body = aux._get_task_extra_body(task) or None
            out[label] = base._scrub(aux._build_call_kwargs(
                provider, model, messages, temperature=0.3, max_tokens=1024, tools=base.TOOLS, timeout=30.0,
                extra_body=extra_body, reasoning_config=reasoning, base_url=base_url, task=task))
    return out


@pytest.mark.parametrize("key,provider,model,base_url,agent_kwargs", MODEL_VARIANTS,
                         ids=[c[0] for c in MODEL_VARIANTS])
def test_model_variant_wire_matches_snapshot(offline, key, provider, model, base_url, agent_kwargs):
    actual = base._wire(provider, model, base_url, reasoning_rows=REASONING_LADDER, **agent_kwargs)
    meta = {"provider": provider, "model": model, "base_url": base_url, "agent_kwargs": agent_kwargs}
    base._check(key, actual, meta, snapshot=SNAPSHOT, cell_keys=CELL_KEYS)


@pytest.mark.parametrize("key,provider,model,base_url,attrs", STREAM_CELLS, ids=[c[0] for c in STREAM_CELLS])
def test_stream_kwargs_match_snapshot(offline, key, provider, model, base_url, attrs):
    actual = _stream_delta(provider, model, base_url, attrs)
    meta = {"provider": provider, "model": model, "base_url": base_url, "agent_attrs": attrs}
    base._check(key, actual, meta, snapshot=SNAPSHOT, cell_keys=CELL_KEYS)


@pytest.mark.parametrize("key,provider,model,base_url,opts", AUX_CELLS, ids=[c[0] for c in AUX_CELLS])
def test_aux_call_kwargs_match_snapshot(offline, monkeypatch, key, provider, model, base_url, opts):
    actual = _aux_kwargs(monkeypatch, provider, model, base_url, opts)
    meta = {"provider": provider, "model": model, "base_url": base_url, "aux_options": opts}
    base._check(key, actual, meta, snapshot=SNAPSHOT, cell_keys=CELL_KEYS)


def test_variant_snapshot_has_no_orphans():
    recorded = set(base._load(SNAPSHOT))
    assert CELL_KEYS <= recorded, f"cells without a recorded wire: {sorted(CELL_KEYS - recorded)}"
    assert recorded <= CELL_KEYS, f"snapshot entries for cells that no longer exist: {sorted(recorded - CELL_KEYS)}"
