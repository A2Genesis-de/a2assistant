"""Local shared-metrics JSON-RPC handlers: the collection switch (``telemetry.shared_metrics.enabled``)
and the client-side events Desktop and the Ink TUI report into the local store.
Bodies are rebound onto server.py's globals (method_ctx.bind_module) and reference them bare.
"""

import logging

from .method_ctx import HandlerRegistry, bind_module

logger = logging.getLogger(__name__)
_registry = HandlerRegistry()
method = _registry.method
_profile_scoped = _registry.profile_scoped


def _tui_model_friction(signal, session, turns=1):
    from hermes_cli.observability.shared_metrics_model import record_model_friction
    record_model_friction(
        signal, session_id=session.get("session_key"), agent=session.get("agent"),
        hermes_home=session.get("profile_home"), turns=turns)


def _shared_metrics_enabled(cfg) -> bool:
    telemetry = cfg.get("telemetry") if isinstance(cfg, dict) else None
    shared = telemetry.get("shared_metrics") if isinstance(telemetry, dict) else None
    return isinstance(shared, dict) and shared.get("enabled") is True


@method("shared_metrics.status")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """``{enabled}``: whether the focused profile collects shared metrics locally."""
    try:
        return _ok(rid, {"enabled": _shared_metrics_enabled(_load_cfg())})
    except Exception as e:
        return _err(rid, 5095, str(e))


@method("shared_metrics.slash_command")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """The Desktop and Ink TUI dispatchers call this once per user-typed slash command, locally
    handled ones included; the gateway never counts slash.exec / command.dispatch itself, so
    each command lands exactly once. Always ``{ok: true}`` (the events API never raises)."""
    from hermes_cli.observability.shared_metrics_events import record_slash_command

    record_slash_command(command=str(params.get("command") or ""), surface=_resolve_session_platform())
    return _ok(rid, {"ok": True})


@method("shared_metrics.startup_latency")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """The Ink TUI (gateway ready) and Desktop (backend attached) each report their own launch ->
    ready time once per launch; ``launch_id`` latches it here too, so a reconnect to this backend
    never re-counts. A Desktop on a URL/cloud backend has no ``HERMES_DESKTOP`` here, so the
    client's declared surface wins over env detection. Always ``{ok: true}``."""
    from hermes_cli.observability.shared_metrics_startup import record_rpc_startup_latency

    record_rpc_startup_latency(
        client_surface=params.get("surface") or _resolve_session_platform(), elapsed_ms=params.get("elapsed_ms"),
        launch_id=params.get("launch_id"),
    )
    return _ok(rid, {"ok": True})


# ---- v4 reliability ----
@method("shared_metrics.update_run")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """Desktop reports each packaged self-update once (a pending record survives the restart that
    applies it and is sent on the next backend attach). Always ``{ok: true}``."""
    from hermes_cli.observability.shared_metrics_update import record_desktop_update

    record_desktop_update(
        outcome=params.get("outcome"), failed_stage=params.get("failed_stage"),
        duration_ms=params.get("duration_ms"), mechanism=params.get("mechanism"),
        from_commit_date=params.get("from_commit_date"),
    )
    return _ok(rid, {"ok": True})
# ---- end v4 reliability ----


# ---- v5 desktop ----
@method("shared_metrics.desktop_feature_use")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """Desktop reports each area the user opened, at most once per UTC day (latched on both sides).
    Always ``{ok: true}``; a no-op unless shared metrics are on."""
    from hermes_cli.observability.shared_metrics_desktop import record_desktop_feature_use

    record_desktop_feature_use(area=params.get("area"))
    return _ok(rid, {"ok": True})


@method("shared_metrics.desktop_friction")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """One Desktop friction event (dismissed notice, error toast by category, renderer crash, backend
    disconnect, slow frame), capped per day. Always ``{ok: true}``."""
    from hermes_cli.observability.shared_metrics_desktop import record_desktop_friction

    record_desktop_friction(kind=params.get("kind"), detail=params.get("detail"))
    return _ok(rid, {"ok": True})


@method("shared_metrics.desktop_onboarding")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """One Desktop first-run step transition, once per (step, event) per profile. Always ``{ok: true}``."""
    from hermes_cli.observability.shared_metrics_desktop import record_desktop_onboarding

    record_desktop_onboarding(step=params.get("step"), event=params.get("event"))
    return _ok(rid, {"ok": True})


@method("shared_metrics.desktop_dislike")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """One Desktop dislike signal (quick close, cancelled flow, setting changed vs default, rage click,
    undo, feature disabled), capped per signal per day. For a setting the backend reads the saved value
    and compares it to the default itself; only the key and the direction are recorded."""
    from hermes_cli.observability.shared_metrics_desktop import record_desktop_dislike

    record_desktop_dislike(signal=params.get("signal"), target=params.get("target"), setting=params.get("setting"))
    return _ok(rid, {"ok": True})


@method("shared_metrics.desktop_daily")
@_profile_scoped
def _(rid, params: dict) -> dict:
    """One finished Desktop day: mode use (Bot Mode vs Sessions, with the bot count) and button presses
    per action. ``{recorded: true}`` once settled, so the client drops the day; false keeps it."""
    from hermes_cli.observability.shared_metrics_desktop import record_desktop_daily

    recorded = record_desktop_daily(
        day=params.get("day"), modes=params.get("modes"), actions=params.get("actions"),
        bot_count=params.get("bot_count"),
    )
    return _ok(rid, {"recorded": recorded})
# ---- end v5 desktop ----


def register(server) -> None:
    bind_module(globals(), server, skip=("_",))
