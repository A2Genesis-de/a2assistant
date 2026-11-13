"""Provider-specific runtime builders for :mod:`hermes_cli.runtime_provider`: the OpenRouter /
bare-custom fallback resolver and external-process providers. Origin-internal collaborators are
resolved on the origin module at call time via :func:`_rp` so test patches on
``hermes_cli.runtime_provider.*`` (``_get_model_config``, ``load_config``, ``has_usable_secret``,
``_try_resolve_from_custom_pool``, …) still apply."""

from __future__ import annotations

from typing import Any, Optional

from agent.secret_scope import get_secret_str
from hermes_constants import OPENROUTER_BASE_URL
from utils import base_url_host_matches, base_url_hostname, base_url_origin


def _rp():
    import hermes_cli.runtime_provider as origin
    return origin


# ── OpenRouter / bare custom fallback ──────────────────────────────────────────────────────


def _resolve_openrouter_runtime(
    *, requested_provider: str, explicit_api_key: Optional[str] = None, explicit_base_url: Optional[str] = None
) -> dict[str, Any]:
    """Terminal resolver: OpenRouter, or a bare/aliased ``custom`` endpoint. base_url precedence:
    explicit > CUSTOM_BASE_URL > trusted ``model.base_url`` > OPENROUTER_BASE_URL > default.
    OPENAI_BASE_URL never picks the endpoint (config.yaml is the single source of truth for endpoint
    URLs); it is read only to keep an OPENAI_API_KEY bound to another host out of the OpenRouter
    fallback. OpenRouter contexts prefer OPENROUTER_API_KEY; custom endpoints never receive the
    OpenRouter key and only get env keys gated on their authoritative hosts."""
    rp = _rp()
    model_cfg = rp._get_model_config()
    cfg_base_url = model_cfg.get("base_url") if isinstance(model_cfg.get("base_url"), str) else ""
    cfg_provider = (model_cfg.get("provider") if isinstance(model_cfg.get("provider"), str) else "").strip().lower()
    cfg_api_key = next((v.strip() for v in (model_cfg.get("api_key"), model_cfg.get("api")) if isinstance(v, str) and v.strip()), "")
    requested_norm = (requested_provider or "").strip().lower()
    # Aliases resolving to "custom" (ollama, vllm, …) follow bare-custom trust + routing rules.
    if requested_norm and requested_norm != "custom" and rp._resolves_to_custom(requested_norm):
        requested_norm = "custom"
    env_openrouter_base_url = get_secret_str("OPENROUTER_BASE_URL", "").strip()
    env_custom_base_url = get_secret_str("CUSTOM_BASE_URL", "").strip()
    use_config_base_url = bool(cfg_base_url.strip()) and not explicit_base_url and (
        (requested_norm == "auto" and cfg_provider in ("", "auto"))
        or (requested_norm == "custom" and rp._config_base_url_trustworthy_for_bare_custom(cfg_base_url, cfg_provider))
        # provider: openrouter + base_url in config.yaml is a deliberate mirror/proxy (#10622).
        or (requested_norm == "openrouter" and cfg_provider == "openrouter")
    )
    base_url = ((explicit_base_url or "").strip() or env_custom_base_url or (cfg_base_url.strip() if use_config_base_url else "")
                or env_openrouter_base_url or OPENROUTER_BASE_URL).rstrip("/")
    # Choose API key based on whether the resolved base_url targets OpenRouter. When hitting OpenRouter,
    # prefer OPENROUTER_API_KEY (issue #289). When hitting a custom endpoint (e.g. Z.ai, local LLM), prefer
    # OPENAI_API_KEY so the OpenRouter key doesn't leak to an unrelated provider (issues #420, #560).
    is_openrouter_url = base_url_host_matches(base_url, "openrouter.ai")
    # Explicitly-configured OpenRouter mirrors (OPENROUTER_BASE_URL, or a config.yaml base_url under
    # provider: openrouter) still count as OpenRouter for key selection — otherwise the mirror's host
    # fails the openrouter.ai match and the generic custom-endpoint branch never selects
    # OPENROUTER_API_KEY for it (#10622).
    is_openrouter_context = is_openrouter_url or (
        requested_norm == "openrouter" and (
            (use_config_base_url and cfg_provider == "openrouter" and base_url == cfg_base_url.strip().rstrip("/"))
            or ((env_openrouter_base_url or base_url == env_openrouter_base_url)
                and base_url == (env_openrouter_base_url or "").rstrip("/"))
        )
    )
    # A bare ``custom`` route to a URL a ``providers:`` entry owns, when that entry declares a credential:
    # the entry's key replaces the implicit env keys (on its built-in's host those are another account's).
    from hermes_cli.runtime_provider_custom import _model_cfg_key_env_for, _owning_entry_credential
    declared, entry_key = _owning_entry_credential(rp, base_url) if requested_norm == "custom" else (False, "")
    if is_openrouter_context:
        # Same read order as the credential pool and _resolve_api_key_provider_secret
        # (.env, then scope-aware os.environ, raw op:// references yielding to the resolved
        # scoped value). get_secret_str sees os.environ only, so a key living solely in
        # ~/.hermes/.env was lost once the pool entry went exhausted/benched (#117667).
        # OPENAI_API_KEY is a legacy home for an OpenRouter key. When OPENAI_BASE_URL binds it, it
        # goes only to that origin: another scheme or port on the same host is another endpoint.
        # Unbound, openrouter.ai gets it only when it is OpenRouter-shaped (sk-or-), so a real OpenAI
        # key never reaches a third party.
        from hermes_cli.config import get_env_value_prefer_dotenv
        openai_key = get_env_value_prefer_dotenv("OPENAI_API_KEY") or ""
        openai_base_url = get_secret_str("OPENAI_BASE_URL", "").strip()
        if base_url_hostname(openai_base_url):
            openai_origin = base_url_origin(openai_base_url)  # empty on a bad port: bound, matches nothing
            openai_key_ok = bool(openai_origin[1]) and openai_origin == base_url_origin(base_url)
        else:
            openai_key_ok = not is_openrouter_url or rp.looks_like_openrouter_key(openai_key)
        candidates = [explicit_api_key]
        if not declared:  # an owning entry's declared credential replaces the implicit env keys
            candidates += [get_env_value_prefer_dotenv("OPENROUTER_API_KEY"), openai_key if openai_key_ok else ""]
    else:
        # ``model.api_key`` and ``model.key_env`` back a trusted config base_url only; the key_env
        # rung is what a bare ``provider: custom`` block relies on (#67453).
        candidates = [explicit_api_key, (cfg_api_key if use_config_base_url else ""),
                      (_model_cfg_key_env_for(model_cfg, base_url) if use_config_base_url else ""),
                      *([] if declared else rp._host_gated_env_key_candidates(base_url, ollama=True))]
    api_key = next((str(c or "").strip() for c in candidates if rp.has_usable_secret(c)), "") or entry_key
    source = "explicit" if (explicit_api_key or explicit_base_url) else "env/config"
    cfg_api_mode = rp._parse_api_mode(model_cfg.get("api_mode"))
    # Explicit "custom" stays "custom" rather than relabeling to "openrouter".
    if requested_norm != "custom":
        return rp._runtime("openrouter", cfg_api_mode or rp._detect_api_mode_for_url(base_url) or "chat_completions", base_url,
                           api_key, source=source)
    # An explicit launch key is the operator's credential for this route and wins over the pool (R2-M1).
    if base_url and not rp.has_usable_secret(explicit_api_key):
        pool_result = rp._try_resolve_from_custom_pool(base_url, "custom", cfg_api_mode, provider_name=None)
        if pool_result:
            return pool_result
    # Local no-auth servers get a placeholder key — the OpenAI SDK requires a non-empty string.
    if not api_key and not is_openrouter_url:
        api_key = "no-key-required"
    return rp._runtime("custom", rp._resolve_plain_custom_api_mode(model_cfg, base_url), base_url, api_key, source=source)


# ── External-process (agent CLI over stdio, e.g. ACP) ──────────────────────────────────────


def _is_external_process_provider(provider: str) -> bool:
    """Keyed on the registered provider's auth_type (CLI registry first, then the profile registry
    so the check works before the CLI registry has been extended)."""
    name = (provider or "").strip().lower()
    if not name:
        return False
    try:
        pconfig = _rp().PROVIDER_REGISTRY.get(name)
        if pconfig is not None:
            return pconfig.auth_type == "external_process"
    except Exception:
        pass
    try:
        from providers import get_provider_profile

        profile = get_provider_profile(name)
    except Exception:
        return False
    return profile is not None and getattr(profile, "auth_type", "") == "external_process"


def _resolve_external_process_runtime(provider: str, requested_provider: str) -> dict[str, Any]:
    rp = _rp()
    creds = rp.resolve_external_process_provider_credentials(provider)
    return rp._runtime(provider, "chat_completions", creds.get("base_url", "").rstrip("/"), creds.get("api_key", ""),
                       command=creds.get("command", ""), args=list(creds.get("args") or []),
                       source=creds.get("source", "process"), requested_provider=requested_provider)
