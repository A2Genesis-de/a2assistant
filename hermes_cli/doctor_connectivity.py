"""API connectivity probes for ``hermes doctor`` (split out of ``doctor.py``).

Every probe is a pure function: one HTTP/SDK call returning a ``ProbeResult`` with the row(s) to
print and issue strings to append. No printing inside workers — the caller prints in submission order.
"""

from __future__ import annotations

import concurrent.futures
import errno
import functools
import os
import socket
from typing import NamedTuple
from urllib.parse import urlsplit

from hermes_cli.colors import Colors, color
from hermes_cli.version_info import hermes_user_agent
from hermes_constants import OPENROUTER_MODELS_URL
from utils import normalize_proxy_env_vars

_APIKEY_PROVIDERS_CACHE: list | None = None


class ProbeResult(NamedTuple):
    label: str
    lines: list  # [(glyph, label, detail)]
    issues: list


_GLYPH = {"ok": ("✓", Colors.GREEN), "warn": ("⚠", Colors.YELLOW), "fail": ("✗", Colors.RED)}


def _row(name: str, status: str, detail: str = "", issues: list | None = None, label: str | None = None) -> ProbeResult:
    glyph, col = _GLYPH[status]
    return ProbeResult(name, [(color(glyph, col), name if label is None else label, color(detail, Colors.DIM) if detail else "")],
                       list(issues or []))


def _skip(name: str) -> ProbeResult:
    return ProbeResult(name, [], [])


def _build_apikey_providers_list() -> list:
    """Build the API-key provider health-check list once and cache it.

    Tuple format: (name, env_vars, default_url, base_env, supports_models_endpoint), one row per
    ProviderProfile with auth_type="api_key" — adding plugins/model-providers/<name>/ is sufficient to
    get into doctor.
    """
    _static: list = []
    # Providers with a dedicated health check (custom headers/auth): skip their pluggable profiles so
    # the generic Bearer loop doesn't run a duplicate, broken check (Anthropic needs x-api-key).
    _dedicated_canonical = {"anthropic", "openrouter"}
    try:
        from providers import list_providers
        from providers.base import ProviderProfile as _PP
        try:
            from hermes_cli.providers import normalize_provider as _normalize_provider
        except Exception:  # pragma: no cover - normalization is best-effort
            def _normalize_provider(_name: str) -> str:
                return (_name or "").strip().lower()
        for _pp in list_providers():
            if not isinstance(_pp, _PP) or _pp.auth_type != "api_key" or not _pp.env_vars:
                continue
            _label = _pp.display_name or _pp.name
            if _pp.name in _dedicated_canonical or {_normalize_provider(a) for a in (_pp.name, *(_pp.aliases or ()))} & _dedicated_canonical:
                continue
            # Key vars vs base-URL vars: the first found value goes out as Authorization: Bearer, never a URL.
            _is_url = lambda v: v.endswith("_BASE_URL") or v.endswith("_URL")
            _key_vars = tuple(v for v in _pp.env_vars if not _is_url(v))
            if not _key_vars:
                continue
            _base_var = next((v for v in _pp.env_vars if _is_url(v)), None)
            _models_url = (_pp.models_url or (_pp.base_url.rstrip("/") + "/models")) if _pp.base_url else None
            _static.append((_label, _key_vars, _models_url, _base_var, getattr(_pp, "supports_health_check", True)))
    except Exception:
        pass
    return _static


# HTTP status -> (detail, issue) for the OpenRouter probe; anything else is a generic HTTP failure.
_OPENROUTER_STATUS = {
    401: ("(invalid API key)", "Check OPENROUTER_API_KEY in .env"),
    402: ("(out of credits — payment required)",
          "OpenRouter account has insufficient credits. "
          "Fix: run 'hermes config set model.provider <provider>' "
          "to switch providers, or fund your OpenRouter account "
          "at https://openrouter.ai/settings/credits"),
    429: ("(rate limited)", "OpenRouter rate limit hit — consider switching to a different provider or waiting"),
}


def _probe_openrouter() -> ProbeResult:
    name = "OpenRouter API"
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return _row(name, "warn", "(not configured)")
    try:
        import httpx
        r = httpx.get(OPENROUTER_MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=10)
    except Exception as e:
        return _row(name, "fail", f"({e})", ["Check network connectivity"])
    if r.status_code == 200:
        return _row(name, "ok")
    detail, issue = _OPENROUTER_STATUS.get(r.status_code, (f"(HTTP {r.status_code})", None))
    return _row(name, "fail", detail, [issue] if issue else None)


def _probe_anthropic() -> ProbeResult:
    name = "Anthropic API"
    from hermes_cli.auth import get_anthropic_key
    key = get_anthropic_key()
    if not key:
        return _skip(name)
    try:
        import httpx
        from agent.anthropic_adapter import _COMMON_BETAS, _OAUTH_ONLY_BETAS, _CONTEXT_1M_BETA
        from agent.anthropic_credentials import _is_oauth_token
        is_oauth = _is_oauth_token(key)
        headers = {"anthropic-version": "2023-06-01", **({"Authorization": f"Bearer {key}", "anthropic-beta": ",".join(_COMMON_BETAS + _OAUTH_ONLY_BETAS)}
                                                         if is_oauth else {"x-api-key": key})}
        url = "https://api.anthropic.com/v1/models"
        r = httpx.get(url, headers=headers, timeout=10)
        # OAuth subscriptions without 1M context reject with 400 "long context beta is not yet available";
        # retry once with that beta stripped so doctor doesn't falsely report Anthropic as unreachable.
        if is_oauth and r.status_code == 400 and "long context beta" in r.text.lower() and "not yet available" in r.text.lower():
            headers["anthropic-beta"] = ",".join([b for b in _COMMON_BETAS if b != _CONTEXT_1M_BETA] + list(_OAUTH_ONLY_BETAS))
            r = httpx.get(url, headers=headers, timeout=10)
    except Exception as e:
        return _row(name, "warn", f"({e})")
    return _row(name, *{200: ("ok",), 401: ("fail", "(invalid API key)")}.get(r.status_code, ("warn", "(couldn't verify)")))


def _probe_apikey_provider(pname, env_vars, default_url, base_env, supports_health_check) -> ProbeResult:
    key = next((k for k in (os.getenv(ev, "") for ev in env_vars) if k), "")
    if not key:
        return _skip(pname)
    label = pname.ljust(20)
    if not supports_health_check:
        return _row(pname, "ok", "(key configured)", label=label)
    try:
        import httpx
        base, url, headers = _apikey_request(key, base_env, default_url)
        if base.rstrip("/").endswith("/anthropic"):
            # Anthropic-only gateway (no OpenAI-compat sibling, so no /models): probe the route the runtime uses.
            r = _anthropic_messages_probe(base, key)
            if r.status_code == 400:  # Anthropic-shaped 400 still proves route + auth (#66756)
                return _row(pname, "ok", label=label)
            if r.status_code == 403:
                return _row(pname, "fail", "(access denied)", [f"Check {env_vars[0]} in .env"], label=label)
        else:
            r = httpx.get(url, headers=headers, timeout=10)
    except Exception as e:
        return _row(pname, "warn", f"({e})", label=label)
    if r.status_code == 401:
        return _row(pname, "fail", "(invalid API key)", [f"Check {env_vars[0]} in .env"], label=label)
    return _row(pname, "ok", label=label) if r.status_code == 200 else _row(pname, "warn", f"(HTTP {r.status_code})", label=label)


def _anthropic_messages_probe(base: str, key: str):
    """POST ``<base>/v1/messages`` with ``max_tokens=1`` exactly as the Anthropic adapter would: same
    auth family (Bearer for Azure Foundry, else x-api-key) and the same ``api-version`` query. Azure
    Foundry's ``/anthropic`` route 404s on ``GET /models`` even when chat works (#66756)."""
    import httpx
    from agent.anthropic_adapter import _base_client_kwargs
    from agent.anthropic_endpoints import _requires_bearer_auth
    normalized, kwargs = _base_client_kwargs(base, None)
    auth = {"Authorization": f"Bearer {key}"} if _requires_bearer_auth(normalized) else {"x-api-key": key}
    headers = {"anthropic-version": "2023-06-01", "User-Agent": hermes_user_agent(), **auth}
    model = str(_model_cfg().get("default") or "").strip() or "claude-sonnet-4-5"
    body = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
    return httpx.post(normalized + "/v1/messages", headers=headers, params=kwargs.get("default_query"), json=body, timeout=10)


def _model_cfg() -> dict:
    try:
        from hermes_cli.config import load_config_readonly
        model_cfg = (load_config_readonly() or {}).get("model")
    except Exception:
        return {}
    return model_cfg if isinstance(model_cfg, dict) else {}


def _apikey_request(key: str, base_env, default_url) -> tuple:
    """(effective base, models URL, headers) for a generic Bearer-auth probe, with the per-vendor rewrites."""
    base = os.getenv(base_env, "") if base_env else ""
    # Anthropic-compat endpoints (/anthropic) lack /models — use the OpenAI-compat /v1 surface.
    if base and base.rstrip("/").endswith("/anthropic"):
        from agent.auxiliary_client import _to_openai_base_url
        base = _to_openai_base_url(base)
    url = (base.rstrip("/") + "/models") if base else default_url
    headers = {"Authorization": f"Bearer {key}", "User-Agent": hermes_user_agent()}
    return base, url, headers


def _load_network_config() -> dict:
    try:
        from hermes_cli.config import load_config_readonly
        net = (load_config_readonly() or {}).get("network")
    except Exception:
        return {}
    return net if isinstance(net, dict) else {}


def _tcp_connect(sockaddr, timeout: float) -> None:
    """Open + close one IPv6 TCP connection; raises OSError (TimeoutError on a dead route)."""
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(sockaddr)


_IPV6_PROBE_TIMEOUT = 2.0


def _probe_ipv6_path() -> ProbeResult:
    """Dead-IPv6-route detector (#114265): an advertised AAAA path that only times out makes every
    serial connect burn its full timeout before IPv4 answers. Name the remedy instead of stalling."""
    name = "IPv6 route"
    if _load_network_config().get("force_ipv4"):
        return _skip(name)  # IPv6 is never dialled
    host = urlsplit(OPENROUTER_MODELS_URL).hostname
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        infos = []
    if not infos:
        return _skip(name)  # no AAAA record / no IPv6 resolver: nothing to test
    try:
        _tcp_connect(infos[0][4], _IPV6_PROBE_TIMEOUT)
    except TimeoutError:
        remedy = "set `network.force_ipv4: true` in config.yaml (or fix the IPv6 route)"
        return _row(name, "warn", f"(IPv6 route to {host} advertised but dead: connect timed out after "
                    f"{_IPV6_PROBE_TIMEOUT:g}s — {remedy})",
                    [f"Dead IPv6 route: every IPv6-first connect stalls before IPv4 answers. Fix: {remedy}"])
    except OSError as e:
        if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL):
            return _row(name, "ok", "(no IPv6 route — IPv4 only)")  # fails fast, so no stall
    return _row(name, "ok", f"(IPv6 path to {host} reachable)")  # refused/reset also prove a live path


# /rate_limit is reachable by EVERY token type and does not count against the quota. /user answers
# 403 "Resource not accessible by integration" for App installation tokens (the GITHUB_TOKEN every
# Actions job exports), which would paint a valid token red.
GITHUB_API_PROBE_URL = "https://api.github.com/rate_limit"


def _probe_github_token() -> ProbeResult:
    """Validate a configured ``GITHUB_TOKEN``/``GH_TOKEN`` against api.github.com (#115257).

    A dead PAT in ``.env`` used to fail every git-auth clone with a message that never named the
    token; the resolver now falls through to the gh CLI, and this row tells the user WHICH file
    still carries the stale token so they can remove it.
    """
    name = "GitHub token"
    from hermes_cli.config import get_env_value, load_env
    var = next((v for v in ("GITHUB_TOKEN", "GH_TOKEN") if get_env_value(v)), None)
    if var is None:
        return _skip(name)  # the Skills Hub section already reports gh-CLI / no-token state
    from hermes_cli.doctor import _DHH
    where = f"{_DHH}/.env" if var in load_env() else "the environment"
    try:
        import httpx
        r = httpx.get(GITHUB_API_PROBE_URL, timeout=10, headers={
            "Authorization": f"Bearer {get_env_value(var)}", "User-Agent": hermes_user_agent(),
            "Accept": "application/vnd.github+json"})
    except Exception as e:
        return _row(name, "fail", f"({e})", ["Check network connectivity"])
    if r.status_code == 200:
        return _row(name, "ok", f"({var} from {where} accepted by api.github.com)")
    if r.status_code == 401:
        return _row(name, "fail", f"({var} in {where} rejected by api.github.com — expired or revoked)",
                    [f"{var} in {where} is expired or revoked: remove it (gh CLI login is used instead) or paste a fresh token"])
    return _row(name, "fail", f"(HTTP {r.status_code} from api.github.com)")


def build_probes() -> list:
    """(label, callable) pairs in display order."""
    global _APIKEY_PROVIDERS_CACHE
    if _APIKEY_PROVIDERS_CACHE is None:
        _APIKEY_PROVIDERS_CACHE = _build_apikey_providers_list()
    return [
        ("IPv6 route", _probe_ipv6_path),
        ("OpenRouter API", _probe_openrouter), ("Anthropic API", _probe_anthropic),
        # functools.partial binds each row's args so every callable keeps its own provider.
        *((row[0], functools.partial(_probe_apikey_provider, *row)) for row in _APIKEY_PROVIDERS_CACHE),
        ("GitHub token", _probe_github_token),
    ]


def run_probes(probes: list) -> list:
    """Run every probe in a thread pool; results in submission order.

    Probes are independent HTTP calls; parallel collapses the section to roughly the slowest single
    probe without changing the output.
    """
    normalize_proxy_env_vars()  # a bracketed-IPv6 NO_PROXY entry ([::1], Clash Verge/mihomo) makes every bare
    # trust_env client a probe builds raise InvalidURL at construction (#118159) — sanitize once, before any
    # worker runs, so no probe ever reports "(Invalid port: :1])" as provider downtime.
    # 8 workers is plenty — each probe is one HTTP call plus a TLS handshake.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="doctor-probe") as ex:
        return [f.result() for f in [ex.submit(fn) for _, fn in probes]]
