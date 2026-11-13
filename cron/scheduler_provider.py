"""In-process cron scheduler (the trigger): decides only *when* a due job fires — execution +
delivery stay in cron.scheduler.run_job / _deliver_result."""
from __future__ import annotations

import contextlib
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cap for exponential tick backoff during fd exhaustion (interval doubled per failure).
_EMFILE_BACKOFF_MAX_SECONDS = 15 * 60


# Cap for the exponential tick backoff applied while consecutive ticks fail with fd exhaustion
# (EMFILE/ENFILE, #87644). Base is the tick interval (60s by default); each consecutive EMFILE failure
# doubles the wait, capped here so a still-alive-but-exhausted gateway never sleeps longer than this between
# recovery attempts.
def _backoff_wait_seconds(interval: float, consecutive_failures: int) -> float:
    """Plain ``interval`` while healthy; doubles per fd-exhaustion failure, capped.

    Exponential tick backoff shared by both ticker loops (#87644).
    """
    if consecutive_failures <= 0:
        return interval
    return min(interval * (2 **(consecutive_failures - 1)), _EMFILE_BACKOFF_MAX_SECONDS)


def _note_tick_failure(exc: BaseException, consecutive_failures: int) -> int:
    """On fd exhaustion: reclaim fds and bump the backoff counter; any other failure resets it —
    backoff is reserved for the EMFILE storm.

    Shared by both ticker loops (#87644): on fd exhaustion, attempt reclamation (gc.collect + raise the soft
    nofile limit) so the NEXT tick can succeed, and bump the counter so ``_backoff_wait_seconds`` backs off
    exponentially while the process has no chance of making progress.
    """
    from cron.scheduler import _is_fd_exhaustion, _reclaim_fds_best_effort

    if _is_fd_exhaustion(exc):
        _reclaim_fds_best_effort()
        return consecutive_failures + 1
    return 0


def _guarded_store_write(action, description, *args, **kwargs):
    """Run a ticker status-marker write so a failing store never ends the ticker thread.

    The gateway runs the provider on an unsupervised daemon thread: one escaping exception
    there stops cron silently while the gateway keeps serving (#111010). Heartbeat/error
    markers are diagnostics for ``hermes cron status`` — losing one write to a broken store
    must degrade to a logged warning, not thread death.
    """
    try:
        action(*args, **kwargs)
    except BaseException as e:
        logger.warning("Cron %s write failed: %s", description, e, exc_info=True)


def _profile_entry(entry) -> tuple:
    """Normalize a ``profile_homes`` entry (``(name, home)`` tuple or bare home) to ``(name,
    home)``."""
    return entry if isinstance(entry, tuple) else (None, entry)


def _existing_profile_homes(profile_homes: list) -> list:
    """Drop homes no longer on disk: ticking/heartbeating a deleted home would recreate its
    ``cron/`` workspace and silently resurrect the profile.

    Ticking or heartbeating a deleted home recreates its ``cron/`` workspace (``record_ticker_heartbeat`` ->
    ``ensure_dirs`` -> ``mkdir(parents=True)``) on every 60s cycle, so the "deleted" profile silently comes
    back on disk and in ``hermes profile list`` (#47368). Filtering on directory existence leaves a deleted
    profile's home untouched, which is the correct invariant: a home that does not exist cannot hold jobs to
    fire.
    """
    if callable(profile_homes):
        # Live enumerator (multiplex gateway): a profile created after startup is ticked without a
        # restart; a raising enumerator keeps this cycle at zero homes rather than killing the ticker.
        try:
            profile_homes = list(profile_homes())
        except Exception:
            logger.warning("cron profile enumeration failed; skipping this cycle", exc_info=True)
            return []
    return [entry for entry in profile_homes if Path(_profile_entry(entry)[1]).is_dir()]


def routed_profile_fire(home=None) -> bool:
    """True when a fire runs for a profile OTHER than the process's own.

    Derived from the fire's home itself (``home``, else the task's active ``get_hermes_home()``), never from
    a marker one entry point sets: the desktop ticker (``_profile_cron_scope``), the dashboard's
    manual Run now (``hermes_cli.web_server_cron._cron_store_scope``) and any other caller that
    binds a HERMES_HOME override for a sibling profile all reach ``run_one_job`` the same way, and a
    marker set only in the ticker left the manual path with the original cross-profile leak.

    The desktop backend fires every local profile from one process without setting the
    process-global multiplex flag, so every isolation keyed on ``is_multiplex_active()`` was inert
    for those fires: a sibling profile's ``.env`` landed in the shared ``os.environ`` with
    ``override=True`` and a scope miss read the launch profile's credentials (#107692).
    ``cron.scheduler._install_fire_secret_scope`` turns this into multiplex semantics for exactly
    the span the profile's secret scope covers, and the restart-safe handoff marks the worker
    payload with it. The launch identity is ``get_routing_process_hermes_home()`` (gateway/AGENTS.md
    "One launch-home identity")."""
    from hermes_constants import get_hermes_home, get_routing_process_hermes_home, hermes_home_key

    target = home if home is not None else get_hermes_home()
    return hermes_home_key(target) != hermes_home_key(get_routing_process_hermes_home())


@contextlib.contextmanager
def _profile_cron_scope(home):
    """Scope the calling thread to one profile's home + cron store for the block."""
    from cron.jobs import use_cron_store
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override

    # Record per-profile heartbeat after each tick cycle. Distinguish a COMPLETED cycle (``_tick_error``
    # unset) — where each profile's beat reflects its own outcome, so a yielding profile does not darken
    # healthy siblings — from an aborted one (exception), where no profile completed and all beats are
    # unsuccessful (#32612).
    home_token = set_hermes_home_override(str(home))
    try:
        with use_cron_store(home):
            yield
    finally:
        reset_hermes_home_override(home_token)


class InProcessCronScheduler:
    """Default in-process 60s ticker; ``start()`` blocks until ``stop_event``. ``can_dispatch`` is
    an optional drain gate; skipped ticks leave due jobs intact for the next allowed tick."""

    @property
    def name(self) -> str:
        return "builtin"

    def recover_interrupted(self) -> int:
        """Run profile-local attempt recovery for every provider lifecycle."""
        from cron.executions import recover_interrupted_executions

        return recover_interrupted_executions()

    def fire_due(
        self, job_id: str, *, adapters: Any = None, loop: Any = None, force: bool = False,
        manual: bool = False,
    ) -> bool:
        """Run one job NOW. Store CAS claim (multi-process at-most-once) then shared
        ``run_one_job``. True if THIS caller claimed and processed the attempt (even if the job
        failed); False if the claim was lost or the job is gone. ``manual`` marks an off-tick
        run-now (dashboard trigger): the claim must not stamp ``next_run_at`` as the occurrence,
        or that slot is skipped when it arrives."""
        claimed_job = self.claim_fire(job_id, force=force, manual=manual)
        if claimed_job is None:
            return False
        return self.fire_claimed(claimed_job, adapters=adapters, loop=loop)

    def claim_fire(self, job_id: str, *, force: bool = False, manual: bool = False) -> dict | None:
        """Durably claim one fire + create its audit attempt; ``fire_claimed`` runs the exact
        snapshot."""
        from cron.executions import create_execution, finish_execution, set_execution_occurrence
        from cron.jobs import claim_job_for_fire

        execution = create_execution(job_id, source=self.name)
        claim_kwargs = {"return_job": True}
        if force:
            claim_kwargs["force"] = True
        if manual:
            claim_kwargs["manual"] = True
        try:
            claimed_job = claim_job_for_fire(job_id, **claim_kwargs)
            if isinstance(claimed_job, dict):
                set_execution_occurrence(execution["id"], claimed_job.get("_scheduled_instant"))
        except BaseException as exc:
            finish_execution(
                execution["id"], success=False,
                error=f"Fire claim failed before dispatch: {type(exc).__name__}: {exc}",
            )
            raise
        if not isinstance(claimed_job, dict):
            finish_execution(execution["id"], success=False, error="Fire claim was not acquired")
            return None
        claimed_job["execution_id"] = execution["id"]
        return claimed_job

    def fire_claimed(
        self, claimed_job: dict, *, adapters: Any = None, loop: Any = None,
        cancel_event: Any = None,
    ) -> bool:
        """Run an exact ``claim_fire`` snapshot; ``cancel_event`` lets the caller stop it
        cooperatively (e.g. dashboard lifespan drain)."""
        from cron.scheduler import run_one_job

        run_one_job(claimed_job, adapters=adapters, loop=loop, cancel_event=cancel_event)
        return True

    def start(
        self, stop_event, *, adapters=None, loop=None, interval=60, can_dispatch=None,
        profile_homes=None, profile_adapters=None, default_profile=None, profile_gate=None,
        profile_bot_platforms=None,
    ):
        from cron.scheduler import CronTickYielded
        from cron.scheduler import tick as cron_tick
        from cron.jobs import clear_ticker_error, record_ticker_error, record_ticker_heartbeat
        from cron.scheduler_ownership import register_ticked_homes
        from hermes_constants import get_process_hermes_home
        from cron.dispatch_hold import note_dispatching, note_held

        logger.info("In-process cron scheduler started (interval=%ds)", interval)

        # Multiplex: tick EACH profile's store every cycle, heartbeats/recovery scoped per profile.
        # ── Multiplex profiles ──────────────────────────────────────────── When profile_homes is set
        # (multiplex_profiles on), tick EACH profile's cron store on every tick cycle so secondary-profile
        # jobs actually fire instead of languishing in a store no ticker owns (#69377). Without this, only
        # the process-global HERMES_HOME (the default profile) is ticked. Heartbeats and recovery are also
        # scoped per profile so `hermes cron status` reflects liveness for every profile independently.
        if profile_homes is not None and (callable(profile_homes) or profile_homes):
            self._start_multiplex(
                stop_event, profile_homes=profile_homes, adapters=adapters, loop=loop,
                interval=interval, can_dispatch=can_dispatch, profile_adapters=profile_adapters,
                default_profile=default_profile, profile_gate=profile_gate,
                profile_bot_platforms=profile_bot_platforms,
            )
            return

        # Single-profile ticker: the launch home is the only home this process owns cron for.
        register_ticked_homes([get_process_hermes_home()])

        # Startup recovery and the initial heartbeat run before the guarded loop; a broken
        # store here must not take the whole ticker thread down (#111010) — the loop's own
        # per-tick handling logs, persists the reason and keeps the thread alive.
        try:
            recovered = self.recover_interrupted()
            if recovered:
                logger.warning(
                    "Marked %d interrupted cron execution(s) unknown after restart", recovered
                )
            # Heartbeat before the first sleep so `hermes cron status` sees a live ticker
            # immediately.
            record_ticker_heartbeat()
        except BaseException as e:
            logger.error("Cron startup recovery error: %s", e, exc_info=True)
            _guarded_store_write(
                record_ticker_error, "startup error", f"{type(e).__name__}: {e}"
            )
        # EMFILE backoff: don't hammer the store while fds are exhausted; a clean tick resets it.
        consecutive_failures = 0
        next_tick = time.monotonic()
        while not stop_event.is_set():
            ok = False
            try:
                if can_dispatch is not None and not can_dispatch():
                    logger.debug("Cron dispatch paused while gateway drains existing work")
                    note_held()
                else:
                    note_dispatching()
                    cron_tick(
                        verbose=False, adapters=adapters, loop=loop, sync=False,
                        can_dispatch=can_dispatch,
                    )
                ok = True
            except BaseException as e:
                # BaseException, not Exception: a SystemExit must not silently kill the ticker;
                # KeyboardInterrupt is caught on purpose — shutdown is driven by stop_event.
                # Catch BaseException (not just Exception) so a SystemExit from a misbehaving provider SDK /
                # agent retry path does not kill the ticker thread silently (#32612). KeyboardInterrupt is
                # intentionally caught here too — gateway shutdown is driven by stop_event (set by the main
                # thread's signal handler), not by an exception in this daemon thread, so swallowing it and
                # re-checking stop_event keeps shutdown clean.
                if isinstance(e, CronTickYielded):
                    # Expected while a fresh gateway owns the lock; still recorded for status.
                    logger.info("Cron tick yielded: %s", e)
                else:
                    logger.error("Cron tick error: %s", e, exc_info=True)
                # Persist the reason so `hermes cron status` (separate process) shows WHY.
                _guarded_store_write(
                    record_ticker_error, "tick error", f"{type(e).__name__}: {e}"
                )
                consecutive_failures = _note_tick_failure(e, consecutive_failures)
            # Liveness every iteration; success marker only on a clean tick.
            # EMFILE: reclaim fds + back off exponentially so the exhausted process stops hammering the
            # store while it has no chance of making progress (#87644).
            # Record liveness every iteration; bump the success marker only on a clean tick, so status can
            # tell "alive but failing every tick" from "actually firing jobs" (#32612, #32895).
            _guarded_store_write(record_ticker_heartbeat, "heartbeat", success=ok)
            if ok:
                _guarded_store_write(clear_ticker_error, "error clear")
                consecutive_failures = 0
            wait_for = _backoff_wait_seconds(interval, consecutive_failures)
            next_tick += wait_for
            now = time.monotonic()
            if next_tick < now:
                # Tick overran interval or host was suspended; re-anchor to avoid
                # burst-firing zero-length sleep cycles (#114467).
                next_tick = now + wait_for
            stop_event.wait(max(0.0, next_tick - now))

    def _start_multiplex(
        self, stop_event, *, profile_homes, adapters=None, loop=None, interval=60,
        can_dispatch=None, profile_adapters=None, default_profile=None, profile_gate=None,
        profile_bot_platforms=None,
    ):
        """Tick every profile's store, each scoped via ``_profile_cron_scope``. ``profile_gate(name,
        home)``, when given, is consulted every cycle; a rejected profile is neither ticked nor
        heartbeated."""
        from cron.scheduler import tick as cron_tick
        from cron.scheduler import CronTickYielded, _is_fd_exhaustion
        from cron.scheduler_preflight import (
            SharedRouteAdapters, _primary_profile_routes_for_current_home, has_credential_platform,
        )
        from cron.jobs import clear_ticker_error, record_ticker_error, record_ticker_heartbeat
        from cron.scheduler_ownership import register_ticked_homes
        from cron.dispatch_hold import note_dispatching, note_held_profiles

        initial_homes = _existing_profile_homes(profile_homes)
        register_ticked_homes([_profile_entry(entry)[1] for entry in initial_homes])
        logger.info(
            "Multiplex cron scheduler started for %d profile(s): %s%s",
            len(initial_homes),
            [p[0] if isinstance(p, tuple) else p for p in initial_homes],
            " (re-enumerated every cycle)" if callable(profile_homes) else "",
        )

        def tick_adapters_for(profile_name):
            # Deliver via the profile's OWN adapters; NEVER fall back to the default profile's
            # (wrong bot). A credentialless satellite may ride the PRIMARY adapter only for targets
            # an exact enabled route maps here; else fail closed (delivery skipped this tick).
            if profile_name is None or profile_name == default_profile:
                return adapters
            tick_adapters = (profile_adapters or {}).get(profile_name) or {}
            owned = (profile_bot_platforms or {}).get(profile_name)
            if not has_credential_platform(tick_adapters, owned) and adapters:
                return SharedRouteAdapters(adapters, _primary_profile_routes_for_current_home())
            return tick_adapters

        # Recovery + heartbeat per profile; one broken store must not abort startup for the others.
        # A profile may have been deleted since this snapshot was taken; never recreate a deleted home's
        # cron workspace via the heartbeat below (#47368).
        for entry in initial_homes:
            _, home = _profile_entry(entry)
            try:
                with _profile_cron_scope(home):
                    recovered = self.recover_interrupted()
                    if recovered:
                        logger.warning(
                            "Marked %d interrupted cron execution(s) for profile at %s",
                            recovered, home,
                        )
                    record_ticker_heartbeat()
            except BaseException as e:
                logger.error(
                    "Cron startup recovery error for profile at %s: %s", home, e, exc_info=True
                )

        consecutive_failures = 0
        next_tick = time.monotonic()
        while not stop_event.is_set():
            ok = False
            _tick_error = None
            _profile_errors: dict[str, str] = {}
            # Worst failure this cycle (fd exhaustion wins); backoff applied once per cycle.
            # See #87644.
            _cycle_exc: BaseException | None = None
            # Enumeration and gating run on the ticker thread; a raising gate callable must
            # fail THIS cycle (logged, no heartbeats, NO ticks), not end the thread (#111010).
            # Publish the list only once the gate has filtered it: a partial assignment would
            # tick the ungated set — the exact stand-down the Desktop gate exists for (#100489).
            cycle_homes: list = []
            try:
                enumerated = [_profile_entry(e) for e in _existing_profile_homes(profile_homes)]
                if profile_gate is not None:
                    enumerated = [(name, home) for name, home in enumerated if profile_gate(name, home)]
                cycle_homes = enumerated
                # Republish the owned set BEFORE any tick: the per-profile yield gate asks
                # "do I own cron for this home?" and a profile added or gated out this cycle
                # must be reflected in that answer, not one cycle late.
                register_ticked_homes([home for _name, home in cycle_homes])
            except BaseException as e:
                logger.error("Cron profile enumeration error: %s", e, exc_info=True)
                _tick_error = f"{type(e).__name__}: {e}"
                consecutive_failures = _note_tick_failure(e, consecutive_failures)
            try:
                if can_dispatch is not None and not can_dispatch():
                    logger.debug("Cron dispatch paused while gateway drains existing work")
                    note_held_profiles(cycle_homes)
                else:
                    for _pname, home in cycle_homes:
                        try:
                            with _profile_cron_scope(home):
                                note_dispatching()
                                cron_tick(
                                    verbose=False, adapters=tick_adapters_for(_pname), loop=loop,
                                    sync=False, can_dispatch=can_dispatch,
                                )
                        except CronTickYielded as e:
                            # Yield for THIS profile only; one fresh gateway must not stop others.
                            logger.info("Cron tick yielded for profile at %s: %s", home, e)
                            _profile_errors[str(home)] = f"{type(e).__name__}: {e}"
                        except BaseException as e:
                            # THIS profile only; BaseException as in the single-profile loop.
                            logger.error(
                                "Cron tick error for profile at %s: %s", home, e, exc_info=True
                            )
                            _profile_errors[str(home)] = f"{type(e).__name__}: {e}"
                            if _cycle_exc is None or _is_fd_exhaustion(e):
                                _cycle_exc = e
                    ok = not _profile_errors
                    if _cycle_exc is not None:
                        consecutive_failures = _note_tick_failure(_cycle_exc, consecutive_failures)
            except BaseException as e:
                logger.error("Cron tick error: %s", e, exc_info=True)
                _tick_error = f"{type(e).__name__}: {e}"
                # EMFILE: reclaim fds + exponential backoff (#87644).
                consecutive_failures = _note_tick_failure(e, consecutive_failures)
            # Completed cycle: each profile's own outcome; aborted cycle: all beats unsuccessful.
            for _, home in cycle_homes:
                with _profile_cron_scope(home):
                    _home_ok = _tick_error is None and str(home) not in _profile_errors
                    _guarded_store_write(
                        record_ticker_heartbeat, "heartbeat", success=_home_ok
                    )
                    if _home_ok:
                        _guarded_store_write(clear_ticker_error, "error clear")
                    elif str(home) in _profile_errors:
                        _guarded_store_write(
                            record_ticker_error,
                            "tick error",
                            _profile_errors[str(home)],
                        )
                    elif _tick_error:
                        _guarded_store_write(
                            record_ticker_error, "tick error", _tick_error
                        )
            if ok:
                consecutive_failures = 0
            wait_for = _backoff_wait_seconds(interval, consecutive_failures)
            next_tick += wait_for
            now = time.monotonic()
            if next_tick < now:
                # Tick overran interval or host was suspended; re-anchor to avoid
                # burst-firing zero-length sleep cycles (#114467).
                next_tick = now + wait_for
            stop_event.wait(max(0.0, next_tick - now))
