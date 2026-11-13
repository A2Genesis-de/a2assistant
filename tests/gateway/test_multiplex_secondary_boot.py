"""Secondary-profile boot phase of the multiplexing gateway."""

from __future__ import annotations

import pytest

from gateway.config import GatewayConfig
from gateway.run import GatewayRunner


def _runner():
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(multiplex_profiles=True)
    runner._running = True
    runner.adapters = {}
    runner._failed_platforms = {}
    runner._profile_adapters = {}
    runner._profile_failed_platforms = {}
    runner._background_tasks = set()
    runner._snapshot_profile_busy_modes = lambda *a, **k: None
    runner._platform_lock_takeover_on_start = True
    runner._startup_fail_fatal_config = lambda reason: None
    return runner


@pytest.mark.asyncio
async def test_boot_replays_the_launch_ledger_before_secondaries_and_watchers(monkeypatch, tmp_path):
    """The gateway's idle notification loop (``_async_delegation_watcher``, spawned after this phase)
    reads ``completion_queue`` directly, so the launch profile's durable completions must already
    be queued by the boot hook — in the LAUNCH scope, before any secondary is bound (#123265)."""
    from tools import async_delegation, process_registry as pr_mod
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "launch"))
    monkeypatch.setattr(pr_mod.process_registry, "_completions_restored", False)
    order = []
    monkeypatch.setattr(async_delegation, "restore_undelivered_completions",
                        lambda q: order.append(("restore", async_delegation._db_path())) or 0)
    runner = _runner()

    async def secondaries():
        order.append(("secondaries", None))
        return 0

    runner._start_secondary_profile_adapters = secondaries
    assert await runner._start_secondary_profiles(0, []) == (False, 0)
    assert order == [("restore", tmp_path / "launch" / "state.db"), ("secondaries", None)]
