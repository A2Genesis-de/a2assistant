"""Static provider/model catalog tables (data only — no network).

Curated per-provider model lists, the canonical provider registry, display groups and alias
maps. Split out of ``hermes_cli.models``.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class CuratedFallbackModels(list[str]):
    """A curated list served because the provider's live catalog was unavailable. The disk cache
    treats it as a placeholder, never as the account's real catalog (#107391)."""


# Fallback OpenRouter snapshot used when the live catalog is unavailable, as
# ``(model_id, description shown in menus)``. ``:free`` SKUs are described "free".
_OPENROUTER_DESCRIPTIONS = {
    "anthropic/claude-opus-5-fast": "2x price, higher output speed",
    "anthropic/claude-opus-4.8-fast": "2x price, higher output speed",
    "deepseek/deepseek-v4-pro-0813": "dated snapshot of v4-pro",
    "deepseek/deepseek-v4.1-flash-1017": "dated snapshot of v4.1-flash",
    "deepseek/deepseek-v4-flash-0731": "dated snapshot of v4-flash",
    "moonshotai/kimi-k3": "recommended",
    "z-ai/glm-5.3": "default",
    "z-ai/glm-5.3-flashx": "high-speed tier of glm-5.3-flash",
    "openrouter/pareto-code": "auto-routes to cheapest coder meeting openrouter.min_coding_score",
    "openai/gpt-6-astra-fast": "2x price, priority tier",
    "openai/gpt-6-astra-flex": "0.5x price, flex tier",
    "openai/gpt-6-astra-pro-fast": "2x price, priority tier",
    "openai/gpt-6-astra-pro-flex": "0.5x price, flex tier",
    "stealth/union-alpha": "free, stealth model",
    "stealth/space-bunny-alpha": "free, stealth model",
}
OPENROUTER_MODELS: list[tuple[str, str]] = [
    (mid, _OPENROUTER_DESCRIPTIONS.get(mid, "free" if mid.endswith(":free") else ""))
    for mid in (
        "anthropic/claude-fable-5.2", "anthropic/claude-fable-5.1", "anthropic/claude-fable-5", "anthropic/claude-opus-5.5",
        "anthropic/claude-opus-5", "anthropic/claude-opus-5-fast", "anthropic/claude-opus-4.8", "anthropic/claude-opus-4.8-fast",
        "anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5", "anthropic/claude-haiku-5.5", "anthropic/claude-haiku-4.5",
        "openai/gpt-6-astra", "openai/gpt-6-astra-fast", "openai/gpt-6-astra-flex", "openai/gpt-6-astra-pro",
        "openai/gpt-6-astra-pro-fast", "openai/gpt-6-astra-pro-flex",
        "openai/gpt-6.1-sol", "openai/gpt-6.1-sol-pro", "openai/gpt-6.1-terra", "openai/gpt-6-sol", "openai/gpt-6-sol-pro",
        "openai/gpt-6-luna", "openai/gpt-6-luna-pro",
        "openai/gpt-5.5", "openai/gpt-5.5-pro", "openai/gpt-5.4-mini", "google/gemini-4-argon",
        "google/gemini-3.1-pro-preview",
        "google/gemini-3.8-flash", "google/gemini-3.7-flash", "x-ai/grok-4.7", "x-ai/grok-4.6",
        "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-pro-0813", "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017",
        "deepseek/deepseek-v4-flash-0731",
        "qwen/qwen3.8-max-0902", "qwen/qwen3.8-flash", "moonshotai/kimi-k3", "minimax/minimax-m3", "z-ai/glm-5.3",
        "z-ai/glm-5.3-flash", "z-ai/glm-5.3-flashx", "z-ai/glm-5.2",
        "xiaomi/mimo-v2.6-pro", "xiaomi/mimo-v2.6-flash", "xiaomi/mimo-v2.6-pro-ultraspeed", "xiaomi/mimo-v2.5-pro", "tencent/hy4-preview",
        "tencent/hy3",
        "stepfun/step-3.7-flash", "nvidia/nemotron-3-super-120b-a12b", "meta/muse-spark-1.2",
        "meta/muse-spark-1.2-contributor", "meta/muse-spark-1.3", "meta/muse-spark-1.3-contributor", "sakana/fugu-ultra",
        "upstage/solar-pro4", "upstage/solar-mini4",
        "openrouter/pareto-code", "thinkingmachines/inkling:free", "thinkingmachines/inkling-small:free",
        "minimax/minimax-m3:free", "z-ai/glm-5.2:free", "poolside/laguna-s-2.1:free", "poolside/laguna-xs-2.1:free",
        "nvidia/nemotron-3-super-120b-a12b:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
        "inclusionai/ling-3.0-flash:free", "nvidia/nemotron-3.5-lightning:free", "stealth/union-alpha",
        "stealth/space-bunny-alpha",
    )
]

# OpenRouter entries the Nous Portal does not carry (routing/fast variants, free tier —
# ``stealth/union-alpha`` is a $0 stealth SKU without the ``:free`` suffix).
_OPENROUTER_ONLY = {
    "anthropic/claude-opus-5-fast", "anthropic/claude-opus-4.8-fast",
    "meta/muse-spark-1.2-contributor", "meta/muse-spark-1.3-contributor", "openrouter/pareto-code",
    "stealth/union-alpha",
}


def _codex_curated_models() -> list[str]:
    """openai-codex curated list from codex_models.py (DEFAULT_CODEX_MODELS + forward-compat
    synthesis) so the gateway /model picker and the CLI ``hermes model`` flow share one source."""
    from hermes_cli.codex_models import DEFAULT_CODEX_MODELS, _finalize_codex_models
    return _finalize_codex_models(list(DEFAULT_CODEX_MODELS))


# Static xAI fallback when the models.dev disk cache is empty (fresh install, offline first run).
# Mirrors the xAI-direct IDs from $HERMES_HOME/models_dev_cache.json; the cache overrides it on the
# next refresh. Models xAI retired on 2026-05-15 (grok-4*, grok-4-fast*, grok-4-1-fast*,
# grok-code-fast-1) are excluded — see docs.x.ai/developers/migration/may-15-retirement.
_XAI_STATIC_FALLBACK: list[str] = [
    "grok-4.6", "grok-build-0.1", "grok-4.5", "grok-4.3", "grok-4.20-0309-reasoning",
    "grok-4.20-0309-non-reasoning", "grok-4.20-multi-agent-0309",
]

# Callable via xAI OAuth but omitted from models.dev and /v1/models listings. grok-4.6 / grok-4.5
# stay here until the models.dev disk cache refreshes.
_XAI_CURATED_EXTRAS: list[str] = ["grok-4.6", "grok-4.5", "grok-composer-2.5-fast"]

_XAI_TOP_MODEL = "grok-4.6"


def _xai_promote_top(ids: list[str]) -> list[str]:
    """Pin the headline xAI model to the top of the curated list."""
    if _XAI_TOP_MODEL in ids:
        return [_XAI_TOP_MODEL] + [m for m in ids if m != _XAI_TOP_MODEL]
    return ids


def _xai_merge_curated_extras(ids: list[str]) -> list[str]:
    """Append Hermes-curated xAI models missing from models.dev, right after the pinned headline."""
    out = list(ids)
    for extra in _XAI_CURATED_EXTRAS:
        if extra not in out:
            out.insert(1 if out and out[0] == _XAI_TOP_MODEL else len(out), extra)
    return out


def _xai_finalize_catalog(ids: list[str]) -> list[str]:
    return _xai_promote_top(_xai_merge_curated_extras(ids))


def _xai_curated_models() -> list[str]:
    """Offline curated floor for the xAI OAuth picker: $HERMES_HOME/models_dev_cache.json
    (no network), else ``_XAI_STATIC_FALLBACK``. Any failure falls through to the static list.
    Reads through the process-wide models.dev copy, so the parse is the one every later reader shares."""
    try:
        from agent.models_dev import fetch_models_dev
        data = fetch_models_dev(allow_network=False)
        xai = data.get("xai") if isinstance(data, dict) else None
        models = xai.get("models") if isinstance(xai, dict) else None
        if isinstance(models, dict) and models:
            ids = [mid for mid in models if isinstance(mid, str)]
            if ids:
                return _xai_finalize_catalog(sorted(ids))
    except Exception:
        pass
    return _xai_finalize_catalog(list(_XAI_STATIC_FALLBACK))


_XAI_ROWS = ("xai-oauth",)


class _CuratedCatalog(dict):
    """``_PROVIDER_MODELS``: static rows, except xAI's, which come from the models.dev disk cache.

    That cache is a full parse of the whole catalog (tens of MiB resident), so it is read on the first
    lookup of an xAI row or a whole-table walk, never at import: a process that never asks for xAI
    never pays for it. Until then the xAI rows hold the static fallback, and they are filled in place,
    so a list handed out earlier sees the same ids. Overriding ``__iter__`` keeps ``dict(table)`` and
    ``{**table}`` on the slow path that reads values through ``__getitem__``."""

    _xai_ready = False

    def _ensure_xai(self) -> None:
        if self._xai_ready:
            return
        ids = _xai_curated_models()
        for row in _XAI_ROWS:
            current = dict.get(self, row)
            if isinstance(current, list):
                current[:] = ids
        self._xai_ready = True

    def __iter__(self):
        return dict.__iter__(self)

    def __getitem__(self, key):
        if key in _XAI_ROWS:
            self._ensure_xai()
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        if key in _XAI_ROWS:
            self._ensure_xai()
        return dict.get(self, key, default)

    def values(self):
        self._ensure_xai()
        return dict.values(self)

    def items(self):
        self._ensure_xai()
        return dict.items(self)

    def copy(self):
        self._ensure_xai()
        return dict(dict.items(self))


# Native OpenAI Chat Completions (api.openai.com).
_OPENAI_CHAT_MODELS = [
    "gpt-5.4", "gpt-5.4-mini", "gpt-5-mini", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-4.1", "gpt-4o", "gpt-4o-mini",
]
# Curated per-provider lists.
_PROVIDER_MODELS: dict[str, list[str]] = _CuratedCatalog({
    "moa": ["default"],
    "nous": [mid for mid, _ in OPENROUTER_MODELS if mid not in _OPENROUTER_ONLY and not mid.endswith(":free")],
    # Used by /model counts and provider_model_ids fallback when /v1/models is unavailable.
    "openai": list(_OPENAI_CHAT_MODELS),
    "openai-api": [
        "gpt-6.1-sol", "gpt-6.1-sol-pro", "gpt-6-sol", "gpt-6-sol-pro", "gpt-6-luna", "gpt-6-luna-pro",
        "gpt-5.6-sol", "gpt-5.6-sol-pro", "gpt-5.6-terra", "gpt-5.6-terra-pro", "gpt-5.6-luna",
        "gpt-5.6-luna-pro", "gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
        "gpt-5-mini", "gpt-5.3-codex", "gpt-4.1", "gpt-4o", "gpt-4o-mini",
    ],
    "openai-codex": _codex_curated_models(),
    "xai-oauth": _xai_finalize_catalog(list(_XAI_STATIC_FALLBACK)),
    "anthropic": [
        "claude-fable-5-2", "claude-fable-5.1", "claude-fable-5", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5",
        "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
        "claude-sonnet-4-6", "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929",
        "claude-opus-4-20250514", "claude-sonnet-4-20250514", "claude-haiku-4-5-20251001",
    ],
})


# ---------------------------------------------------------------------------
# Canonical provider list — single source of truth for provider identity. Every code path that
# lists, displays, or iterates providers (hermes model, /model, list_authenticated_providers)
# derives from it. slug = internal ID (config.yaml, --provider); label = short display name;
# tui_desc = longer description for the `hermes model` picker.
# ---------------------------------------------------------------------------

class ProviderEntry(NamedTuple):
    slug: str
    label: str
    tui_desc: str


CANONICAL_PROVIDERS: list[ProviderEntry] = [ProviderEntry(*row) for row in (
    ("nous", "Nous Portal", "Nous Portal (Everything your agent needs, 300+ models with bundled tool use)"),
    ("openrouter", "OpenRouter", "OpenRouter (Pay-per-use API aggregator)"),
    ("moa", "Mixture of Agents", "Mixture of Agents (named presets; aggregator acts after reference models)"),
    ("lmstudio", "LM Studio", "LM Studio (Local desktop app with built-in model server)"),
    ("anthropic", "Anthropic", "Anthropic (Claude models via API key or Claude Code)"),
    ("openai-codex", "ChatGPT or Codex Subscription", "ChatGPT or Codex Subscription (Sign in with your ChatGPT account, uses Codex models)"),
    ("openai-api", "OpenAI API", "OpenAI API (api.openai.com, API key)"),
    ("xai-oauth", "xAI Grok OAuth (SuperGrok / Premium+)", "xAI Grok OAuth (SuperGrok / Premium+ subscription)"),
)]


# Auto-extend CANONICAL_PROVIDERS with providers registered under plugins/model-providers/<name>/
# so a new provider reaches the picker, /model and every downstream consumer without edits here.
# Admission is by slug only: every in-tree non-api-key profile (OAuth, external-process, cloud
# SDK) already owns a hand-written row above, so the old auth_type skip set never excluded an
# in-tree provider — it only hid out-of-tree plugins. Visibility is gated downstream by
# credentials, not here: ``models._provider_has_credentials`` / ``_lap_canonical_rows`` route
# through ``auth.get_auth_status`` (external_process → the binary resolves; OAuth → auth.json /
# credential-pool entry), so an admitted row reads authenticated=False until the user signs in.
_canonical_slugs = {p.slug for p in CANONICAL_PROVIDERS}
_BUILTIN_SLUGS = frozenset(_canonical_slugs)


def _plugin_provider_enters_picker(pp) -> bool:
    """Picker admission for a plugin model-provider profile: any slug without a built-in row.

    Every profile is admitted, hidden (pre-release) ones included: ``CANONICAL_PROVIDERS`` is also
    the typed-path registry (``provider:model`` parsing, labels), so a signed-in user must still be
    able to name one. The pickers that list rows filter with ``providers.provider_listed``."""
    return pp.name not in _canonical_slugs


def sync_plugin_provider_catalog() -> int:
    """Admit every registered plugin provider without a built-in row; return how many were added.

    Runs at import and again from ``providers._sync_auth_registry`` whenever a profile is registered
    after this module was imported. The import-time pass alone observes a *partial* registry: a
    plugin whose own imports pull ``hermes_cli.models`` in mid-``_discover_providers()``, or a
    profile registered later at runtime, would otherwise never reach the picker, ``hermes model``,
    ``/model`` or the Desktop ``model.options`` list until restart — the catalog twin of the auth
    registry window (#102123). Idempotent by slug; built-in rows are never rewritten. A row lands
    after its ``picker_after`` slug when that row exists, else at the end.
    """
    try:
        from providers import list_providers
        profiles = list_providers()
    except Exception:
        return 0
    pending = [pp for pp in profiles if _plugin_provider_enters_picker(pp)]
    added = 0
    while pending:
        # Rows anchored on a still-pending row wait for it, so a chain keeps its declared order.
        names = {pp.name for pp in pending}
        ready = [pp for pp in pending if pp.picker_after not in names] or pending
        for pp in ready:
            _admit_plugin_provider(pp)
            added += 1
        pending = [pp for pp in pending if pp not in ready]
    return added


def _admit_plugin_provider(pp) -> None:
    """Add one plugin profile to the picker tables: row (at ``picker_after``), label, group and the
    aggregator set. Its catalog aliases are read per home (:class:`_CatalogAliases`)."""
    label = pp.display_name or pp.name
    entry = ProviderEntry(pp.name, label, pp.description or f"{label} (direct API)")
    slugs = [p.slug for p in CANONICAL_PROVIDERS]
    anchor = pp.picker_after
    CANONICAL_PROVIDERS.insert(slugs.index(anchor) + 1 if anchor in slugs else len(slugs), entry)
    _canonical_slugs.add(pp.name)
    _PROVIDER_LABELS[pp.name] = label
    if pp.picker_group:
        gid, group_label, group_desc = pp.picker_group
        members = PROVIDER_GROUPS.setdefault(gid, (group_label, group_desc, []))[2]
        if pp.name not in members:
            members.append(pp.name)
        _SLUG_TO_GROUP[pp.name] = gid
    if pp.aggregator:
        _AGGREGATOR_PROVIDERS.add(pp.name)


_PROVIDER_LABELS: dict[str, str] = {p.slug: p.label for p in CANONICAL_PROVIDERS}
_PROVIDER_LABELS["custom"] = "Custom endpoint"  # special case: not a named provider


def listed_canonical_providers() -> list[ProviderEntry]:
    """``CANONICAL_PROVIDERS`` minus pre-release profiles the user has not opted into: what a provider
    LIST offers. Typed paths (``provider:model``, labels, ``--provider``) keep the full table."""
    from hermes_cli import models  # the binding every list consumer read before this filter existed
    from providers import unlisted_provider_names
    hidden = unlisted_provider_names()
    return [p for p in models.CANONICAL_PROVIDERS if p.slug not in hidden]


# ---------------------------------------------------------------------------
# Provider groups — DISPLAY ONLY. Vendors with several slugs (global API, China API, OAuth plan,
# ...) fold under one top-level row in the INTERACTIVE PICKERS (``hermes model``, setup wizard,
# Telegram ``/model``). They do NOT change CANONICAL_PROVIDERS, slug identity, ``--provider``,
# ``/model <provider:model>`` or any typed path — every member slug stays individually addressable.
# ``group_providers()`` is the single fold used by all three surfaces.
#   group_id -> (display_label, group_description shown on the collapsed row, [member_slug, ...])
# Member order is the order shown inside the group submenu; member detail lives in ``tui_desc``.
# ---------------------------------------------------------------------------
PROVIDER_GROUPS: dict[str, tuple[str, str, list[str]]] = {
    "openai":   ("OpenAI",          "ChatGPT/Codex subscription or direct OpenAI API", ["openai-codex", "openai-api"]),
}

# Reverse index: member slug -> group_id.
_SLUG_TO_GROUP: dict[str, str] = {
    slug: gid for gid, (_label, _desc, members) in PROVIDER_GROUPS.items() for slug in members
}


def provider_group_for_slug(slug: str) -> str:
    """Return the group_id a provider slug belongs to, or "" if ungrouped."""
    return _SLUG_TO_GROUP.get(str(slug or "").strip().lower(), "")


def group_providers(slugs):
    """Fold a flat ordered slug iterable into picker rows by provider group (DISPLAY ONLY).

    A group row appears at the position of its FIRST present member, in input order; later
    members fold into it. Member order inside a group follows ``PROVIDER_GROUPS`` declaration,
    restricted to the members present in ``slugs``.
    """
    present = {str(slug or "").strip().lower() for slug in slugs}  # same normalisation as the rows below
    group_members = {
        gid: [m for m in members if m in present]
        for gid, (_label, _desc, members) in PROVIDER_GROUPS.items()
    }
    rows = []
    seen: set[str] = set()
    emitted_groups: set[str] = set()
    for slug in slugs:
        s = str(slug or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        gid = _SLUG_TO_GROUP.get(s, "")
        if not gid:
            rows.append({"kind": "single", "slug": s})
            continue
        if gid in emitted_groups:
            continue  # already folded at the first member's position
        emitted_groups.add(gid)
        members = group_members.get(gid) or [s]
        if len(members) <= 1:
            rows.append({"kind": "single", "slug": members[0]})
        else:
            label, desc, _ = PROVIDER_GROUPS[gid]
            rows.append({"kind": "group", "group_id": gid, "label": label,
                         "description": desc, "members": list(members)})
    return rows


class _CatalogAliases(dict):
    """``_PROVIDER_ALIASES``: the built-in alias table plus the ``catalog_aliases`` of the bound home's
    plugin profiles, resolved per read and never copied in: two served homes may give one alias to
    different providers. A built-in alias always wins; among plugins the first registered does."""

    _memo: tuple[tuple, dict[str, str]] = ((), {})

    def _plugin_aliases(self) -> dict[str, str]:
        from providers import bound_registry_key, list_providers
        token = bound_registry_key()
        if self._memo[0] == token:
            return self._memo[1]
        found: dict[str, str] = {}
        for pp in list_providers():
            if pp.catalog_aliases and pp.name not in _BUILTIN_SLUGS:
                for alias in pp.aliases:
                    if not dict.__contains__(self, alias):
                        found.setdefault(alias, pp.name)
        self._memo = (token, found)
        return found

    def __getitem__(self, key: str) -> str:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self._plugin_aliases()[key]

    def get(self, key: str, default: Any = None) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self._plugin_aliases().get(key, default)

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or key in self._plugin_aliases()

    def items(self) -> list[tuple[str, str]]:
        return [*dict.items(self), *self._plugin_aliases().items()]

    def keys(self) -> list[str]:
        return [key for key, _ in self.items()]

    def values(self) -> list[str]:
        return [value for _, value in self.items()]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.items())


_PROVIDER_ALIASES = _CatalogAliases((
    ("claude", "anthropic"), ("claude-code", "anthropic"),
    ("grok-oauth", "xai-oauth"), ("xai-oauth", "xai-oauth"), ("x-ai-oauth", "xai-oauth"), ("xai-grok-oauth", "xai-oauth"),
    ("lmstudio", "lmstudio"), ("lm-studio", "lmstudio"), ("lm_studio", "lmstudio"),
    ("chatgpt", "openai-codex"), ("chatgpt-codex", "openai-codex"),
    ("ollama", "custom"),
    # Local OpenAI-compatible servers route through the generic "custom" provider
    # (parity with hermes_cli.auth and hermes_cli.providers). Issue #62213. The llamacpp
    # aliases stay unmapped: they are the managed local runtime's picker id, and the model
    # validator must reach its staged-library branch before the custom one.
    ("local", "custom"), ("vllm", "custom"),
))


# Offline/fresh-install fallback for the model Hermes silently lands on when the user never picked
# one (GUI onboarding confirm card, empty ``model.default``, provider-set-but-model-missing).
# Deliberately a capable low-cost model rather than the curated lists' entry [0]: aggregator lists are ordered
# most-capable-first, so [0] is the priciest Anthropic flagship.
PREFERRED_SILENT_DEFAULT_MODEL = "z-ai/glm-5.3"


# Providers whose *silent* auto-default goes through the cost-safe catalog-labeled default
# (``get_preferred_silent_default_model``) instead of curated entry [0]. Metered aggregators order
# best-first, so [0] is the priciest flagship; a profile that sets a provider with no model would
# otherwise silently bill the most expensive model (863 Opus requests before one user noticed).
# Network-free (cache-only) on purpose — this is the hot resolution path. The *interactive* default
# (GUI onboarding / ``hermes model``) uses the tier-aware ``get_recommended_default_model`` in
# hermes_cli/web_server.py + ``partition_nous_models_by_tier``, which may hit the Portal.
_SILENT_DEFAULT_PROVIDERS: frozenset[str] = frozenset({"nous", "openrouter"})


# Plugin profiles with ``aggregator=True`` join at sync time (``sync_plugin_provider_catalog``).
_AGGREGATOR_PROVIDERS: set[str] = {"nous", "openrouter"}
sync_plugin_provider_catalog()  # every table it extends is defined above


# Subscription/OAuth providers whose catalogs RE-EXPOSE other vendors' models; tried only as a last
# resort for bare short-alias resolution (after every native-vendor catalog) so they never hijack
# an alias from the model's native vendor. None currently defined.
_BORROWED_MODEL_PROVIDERS: frozenset[str] = frozenset()


# Models supporting OpenAI Priority Processing (service_tier="priority"; see
# openai.com/api-priority-processing). Pattern-based: any OpenAI flagship (gpt-*, o1*, o3*, o4*).
# Non-OpenAI endpoints (OpenRouter/opencode-zen and other proxies) strip service_tier, so false
# positives are harmless. Codex-series models are excluded — the Codex Responses API doesn't
# expose service_tier.
_OPENAI_FAST_MODE_PREFIXES: tuple[str, ...] = ("gpt-", "o1", "o3", "o4")
# OpenAI Ultrafast (service_tier="ultrafast", 6x Standard): GPT-6 Astra and GPT-6.1 Sol
# (developers.openai.com/api/docs/guides/ultrafast-mode, 2026-10-08).
# Exact wire slugs, matched after stripping the vendor prefix and the Hermes-side ``-900k`` alias.
_OPENAI_ULTRAFAST_MODELS: frozenset[str] = frozenset({"gpt-6-astra", "gpt-6.1-sol"})


# Providers where models.dev is authoritative: the curated list is an offline fallback plus custom
# additions the registry lacks, merged fresh-first (curated-only names appended) for both the CLI
# and the gateway /model picker. DELIBERATELY EXCLUDED: "openrouter" (curated list is a hand-picked
# agentic subset of 400+ models — merging would dump everything), "nous" (curated list + Portal
# /models are the subscription-tier source of truth), and providers with dedicated live-endpoint
# branches or a profile catalog hook (anthropic, ai-gateway, ollama-cloud, custom, stepfun, openai-codex).
_MODELS_DEV_PREFERRED: frozenset[str] = frozenset({
    "mistral", "togetherai", "cohere", "perplexity", "groq", "google", "xai-oauth",
})

