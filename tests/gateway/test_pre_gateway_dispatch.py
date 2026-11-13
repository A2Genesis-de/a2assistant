"""Tests for the pre_gateway_dispatch plugin hook.

The hook allows plugins to intercept incoming messages before auth and
agent dispatch. It runs in _handle_message and acts on returned action
dicts: {"action": "skip"|"rewrite"|"allow"}.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.event import MessageEvent
from gateway.session import SessionSource


def _clear_auth_env(monkeypatch) -> None:
    for key in (
        "TELEGRAM_ALLOWED_USERS",
        "GATEWAY_ALLOWED_USERS",
        "TELEGRAM_ALLOW_ALL_USERS",
        "GATEWAY_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(key, raising=False)


def _make_event(text: str = "hello", platform: Platform = Platform.TELEGRAM) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_id="m1",
        source=SessionSource(
            platform=platform,
            user_id="15551234567",
            chat_id="15551234567",
            user_name="tester",
            chat_type="dm",
        ),
    )


def _make_runner(platform: Platform):
    from gateway.run import GatewayRunner

    config = GatewayConfig(
        platforms={platform: PlatformConfig(enabled=True)},
    )
    runner = object.__new__(GatewayRunner)
    runner.config = config
    adapter = SimpleNamespace(send=AsyncMock())
    runner.adapters = {platform: adapter}
    runner.pairing_store = MagicMock()
    runner.pairing_store.is_approved.return_value = False
    runner.pairing_store._is_rate_limited.return_value = False
    runner.session_store = MagicMock()
    runner._running_agents = {}
    return runner, adapter


@pytest.mark.asyncio
async def test_internal_events_bypass_hook(monkeypatch):
    """Internal events (event.internal=True) skip the plugin hook entirely."""
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "*")

    called = {"count": 0}

    def _fake_hook(name, **kwargs):
        called["count"] += 1
        return [{"action": "skip"}]

    async def _capture(event, source, _quick_key, _run_generation):
        return "ok"

    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", _fake_hook)

    runner, _adapter = _make_runner(Platform.TELEGRAM)
    runner._handle_message_with_agent = _capture

    event = _make_event("hi")
    event.internal = True

    # Even though the hook would say skip, internal events bypass it.
    await runner._handle_message(event)
    assert called["count"] == 0

@pytest.mark.asyncio
async def test_hook_fires_without_session_store_attribute(monkeypatch):
    """A runner missing session_store still delivers the event to plugins.

    Regression: the hook kwargs read ``self.session_store`` directly, so a
    partially-initialized runner raised AttributeError inside the dispatch
    try-block — the hook never fired, and every message logged
    "pre_gateway_dispatch invocation failed: 'GatewayRunner' object has no
    attribute 'session_store'". Plugins must receive the event (with
    session_store=None) instead.
    """
    _clear_auth_env(monkeypatch)

    seen = {}

    async def _fake_hook(name, **kwargs):
        if name == "pre_gateway_dispatch":
            seen["session_store"] = kwargs.get("session_store", "MISSING")
            return [{"action": "skip", "reason": "plugin-handled"}]
        return []

    # The inbound path awaits the hook, so the seam is the async entry point.
    monkeypatch.setattr("hermes_cli.plugins.ainvoke_hook", _fake_hook)

    runner, adapter = _make_runner(Platform.TELEGRAM)
    del runner.session_store

    result = await runner._handle_message(_make_event("hi"))
    assert result is None
    # Hook actually fired (skip short-circuited before auth) with a None store.
    assert seen == {"session_store": None}
    adapter.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_hook_callback_is_awaited_on_the_gateway_loop(monkeypatch):
    """An ``async def`` pre_gateway_dispatch callback is awaited on the gateway's own loop.

    Regression: the inbound path called the sync ``invoke_hook``, which (since #109196) runs an
    async callback on a helper thread while the calling loop blocks in ``done.wait()``. A
    callback that awaits anything scheduled on the gateway loop could never complete, and every
    message stalled the loop for the callback's whole duration. Here the callback waits for a
    sibling task on the same loop to release it; that is only possible if the hook is awaited
    in place.
    """
    import asyncio

    _clear_auth_env(monkeypatch)
    gate = asyncio.Event()

    async def _hook(name, **kwargs):
        assert name == "pre_gateway_dispatch"
        await gate.wait()
        return [{"action": "skip", "reason": "gated"}]

    monkeypatch.setattr("hermes_cli.plugins.ainvoke_hook", _hook)

    async def _release():
        await asyncio.sleep(0)
        gate.set()

    runner, adapter = _make_runner(Platform.TELEGRAM)
    asyncio.create_task(_release())
    result = await asyncio.wait_for(runner._handle_message(_make_event("hi")), timeout=5)
    assert result is None
    adapter.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewritten_message_keeps_its_callback_provenance_and_is_admitted(monkeypatch):
    """A rewrite builds a new event. Under ``gateway.multiplex_profiles`` an event without its
    adapter callback's provenance is refused ``invalid_params`` (#139045: every message to a profile
    with a rewriting plugin failed), so the rewritten event must carry the callback's provenance and
    be admitted with the rewritten text."""
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.platforms.event import MessageEvent
    from gateway.run import GatewayRunner
    from gateway.session_authority import SessionAuthority, initialize_session_authority
    from gateway.session_ingress_context import capture_provenance, native_callback, register_transport_home
    from hermes_constants import get_hermes_home
    from hermes_state_runtime import list_session_admissions
    from plugins.platforms.telegram.adapter import TelegramAdapter

    async def rewrite(name, **_kwargs):
        return [{"action": "rewrite", "text": "rewritten"}] if name == "pre_gateway_dispatch" else []

    monkeypatch.setattr("hermes_cli.lifecycle.ainvoke_hook", rewrite)
    monkeypatch.setattr(SessionAuthority, "_schedule", lambda self, ref: None)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "42")
    runner = GatewayRunner(GatewayConfig())
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="fixture-token", typing_indicator=False))
    runner.adapters = {Platform.TELEGRAM: adapter}
    authority = await initialize_session_authority(runner, profile_id="default", instance_id="owner")
    runner._wire_adapter_handlers(adapter)
    # The multiplexed admission check that refused the reporter (thanks @unsupportedpastels).
    runner.config.multiplex_profiles = True
    runner.config._runtime_profile_homes = [("default", get_hermes_home())]
    register_transport_home(runner, None, get_hermes_home())
    source = adapter.build_source(chat_id="42", chat_type="dm", user_id="42")
    human = MessageEvent(text="original", source=source, message_id="h")

    with native_callback(runner, human, get_hermes_home()):
        expected = capture_provenance(runner, human)
        event = await runner._hm_pre_gateway_dispatch_hook(human, source)
        receipt = await authority.admit_native(event)

    payload = list_session_admissions(authority.db, session_id=receipt.ref.session_id, pending_only=False)[-1]["payload"]
    assert expected is not None and event is not human
    assert (payload["text"], payload["native_text_v1"].get("provenance")) == ("rewritten", expected)


@pytest.mark.asyncio
async def test_hook_fires_once_at_messaging_ingress_and_never_when_an_admission_executes(monkeypatch):
    """PLG-5: executing an admitted row (a local CLI/TUI/Desktop turn, or a messaging turn's first
    run or restart replay) re-enters ``_handle_message``. The hook already ran at ingress (main has
    no other firing point), so it must not run again there, and a "skip" never drops admitted input."""
    import gateway.session_authorities as authorities
    import gateway.session_ingress as ingress

    _clear_auth_env(monkeypatch)
    fired = []

    async def hook(name, **kwargs):
        if name != "pre_gateway_dispatch":
            return []
        fired.append(kwargs["event"].text)
        return [{"action": "skip"}] if kwargs["event"].text == "drop me" else []

    async def admit(_authority, event):
        admitted.append(event.text)
        return "admitted"

    admitted = []
    monkeypatch.setattr("hermes_cli.lifecycle.ainvoke_hook", hook)
    monkeypatch.setattr(authorities, "active_authority", lambda _runner: SimpleNamespace(route_epoch=lambda _route: 0))
    monkeypatch.setattr(ingress, "admit_message", admit)
    runner, adapter = _make_runner(Platform.TELEGRAM)
    runner._is_user_authorized_for_source = lambda _s: True
    runner._admit_bot_message_for_source = lambda _s: True
    runner._delivery_adapter_for = runner._intake_adapter_for = lambda _s: adapter
    runner._rescue_orphaned_overflow = lambda _k, _a: None
    runner._enqueue_fifo = MagicMock()
    runner._handle_message_with_agent = AsyncMock(return_value="agent-ok")
    runner._run_post_turn_hooks = AsyncMock()

    assert await runner._handle_message(_make_event("drop me")) is None
    assert await runner._handle_message(_make_event("keep me")) == "admitted"
    assert admitted == ["keep me"] and fired == ["drop me", "keep me"]

    token = ingress.executing_admission.set(True)
    try:
        assert await runner._handle_message(_make_event("drop me")) == "agent-ok"
    finally:
        ingress.executing_admission.reset(token)
    assert fired == ["drop me", "keep me"]


@pytest.mark.asyncio
async def test_webhook_delivery_fires_the_hook_once_at_ingress_before_commit():
    """PLG-5: on main the webhook adapter's ``handle_message`` fired the hook once per delivery,
    before anything ran. Receipt-only ingress (``admit_producer``) must keep that: a skip commits
    nothing, a rewrite is what gets committed and executed, the real drain's execution does not
    fire it again, and a provider retry of a committed delivery is not offered again."""
    import hashlib
    import hmac
    import json

    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from gateway.platforms.webhook import WebhookAdapter
    from hermes_cli.plugins import get_plugin_manager
    from tests.gateway.fixtures.webhook_route_authority import mount_authority
    from tests.waiting import async_wait_until

    fired = []

    def hook(event, **_kwargs):
        fired.append(event.message_id)
        if "drop" in event.text:
            return {"action": "skip"}
        return {"action": "rewrite", "text": "rewritten"} if "rewrite" in event.text else None

    manager = get_plugin_manager()
    manager._discovered = True
    manager._hooks.setdefault("pre_gateway_dispatch", []).append(hook)
    adapter = WebhookAdapter(PlatformConfig(enabled=True, extra={"secret": "owned-secret", "routes": {
        "fixture": {"prompt": "{text}"}}}))
    adapter._deliver_to = AsyncMock()
    app = web.Application()
    mount_authority(app, adapter)
    app.router.add_post("/webhooks/{route_name}", adapter._handle_webhook)

    async def post(client, text, delivery_id):
        body = json.dumps({"text": text}).encode()
        signature = "sha256=" + hmac.new(b"owned-secret", body, hashlib.sha256).hexdigest()
        return await client.post("/webhooks/fixture", data=body, headers={
            "X-GitHub-Delivery": delivery_id, "X-Hub-Signature-256": signature})

    async with TestClient(TestServer(app)) as client:
        runner = adapter._message_handler.__self__
        authority = runner.session_authority
        del authority._schedule  # this test needs the real drain to execute the admitted row
        runner._handle_message_with_agent = AsyncMock(return_value="agent-ok")
        assert (await post(client, "drop this", "d-drop")).status == 202
        assert fired == ["d-drop"] and not authority.db._read_all("SELECT 1 FROM session_admissions")

        assert (await post(client, "keep this", "d-keep")).status == 202
        assert (await post(client, "please rewrite", "d-rewrite")).status == 202
        def settled():
            rows = authority.db._read_all("SELECT request_id, status, payload_json FROM session_admissions")
            return rows if len(rows) == 2 and all(row["status"] == "terminal" for row in rows) else None

        rows = await async_wait_until(settled, what="both admitted deliveries executed")
        assert sorted((row["request_id"], row["status"], json.loads(row["payload_json"])["text"]) for row in rows) == [
            ("d-keep", "terminal", "keep this"), ("d-rewrite", "terminal", "rewritten")]
        executed = sorted(call.args[0].text for call in runner._handle_message_with_agent.await_args_list)
        assert executed == ["keep this", "rewritten"]
        assert (await post(client, "keep this", "d-keep")).status in (200, 202)
    assert fired == ["d-drop", "d-keep", "d-rewrite"]


def _rewriting_hook(fired):
    from hermes_cli.plugins import get_plugin_manager

    def hook(event, **_kwargs):
        fired.append(event.message_id)
        return {"action": "rewrite", "text": "rewritten"} if "rewrite" in event.text else None

    manager = get_plugin_manager()
    manager._discovered = True
    manager._hooks.setdefault("pre_gateway_dispatch", []).append(hook)


def _webhook_app(prompt="{text}"):
    from aiohttp import web

    from gateway.platforms.webhook import WebhookAdapter
    from tests.gateway.fixtures.webhook_route_authority import mount_authority

    adapter = WebhookAdapter(PlatformConfig(enabled=True, extra={"secret": "owned-secret", "routes": {
        "fixture": {"prompt": prompt}}}))
    adapter._deliver_to = AsyncMock()
    app = web.Application()
    mount_authority(app, adapter)
    app.router.add_post("/webhooks/{route_name}", adapter._handle_webhook)
    return adapter, app


async def _post_webhook(client, text, delivery_id):
    import hashlib
    import hmac
    import json

    body = json.dumps(text if isinstance(text, dict) else {"text": text}).encode()
    signature = "sha256=" + hmac.new(b"owned-secret", body, hashlib.sha256).hexdigest()
    return await client.post("/webhooks/fixture", data=body, headers={
        "X-GitHub-Delivery": delivery_id, "X-Hub-Signature-256": signature})


@pytest.mark.asyncio
async def test_a_resend_whose_raw_payload_changed_conflicts_even_when_its_prompt_did_not():
    """The hook sees the parsed provider payload (``raw_message``), not only the rendered prompt. A
    resend under the same delivery id whose prompt renders the same but whose raw field the hook
    rewrote from changed is refused: no duplicate receipt, no second hook call, no second row. The
    exact resend keeps its receipt, and so does a delivery rewritten to empty text."""
    import json

    from aiohttp.test_utils import TestClient, TestServer
    from hermes_cli.plugins import get_plugin_manager

    fired = []

    def hook(event, **_kwargs):
        fired.append(event.raw_message["detail"])
        return {"action": "rewrite", "text": event.raw_message["detail"].replace("blank", "")}

    manager = get_plugin_manager()
    manager._discovered = True
    manager._hooks.setdefault("pre_gateway_dispatch", []).append(hook)
    adapter, app = _webhook_app(prompt="{action}")
    async with TestClient(TestServer(app)) as client:
        authority = adapter._message_handler.__self__.session_authority
        for delivery_id, detail in (("d-1", "handle one"), ("d-2", "blank")):
            assert (await _post_webhook(client, {"action": "opened", "detail": detail}, delivery_id)).status == 202
            retry = await _post_webhook(client, {"action": "opened", "detail": detail}, delivery_id)
            assert (retry.status, (await retry.json())["status"]) == (200, "duplicate")
        changed = await _post_webhook(client, {"action": "opened", "detail": "handle two"}, "d-1")
        assert changed.status == 503
        rows = authority.db._read_all("SELECT request_id, payload_json FROM session_admissions")
    assert sorted((row["request_id"], json.loads(row["payload_json"])["text"]) for row in rows) == [
        ("d-1", "handle one"), ("d-2", "")]
    assert fired == ["handle one", "blank"]


@pytest.mark.asyncio
async def test_rewritten_webhook_delivery_retries_to_its_receipt_and_a_changed_one_is_refused():
    """The committed payload of a rewritten delivery differs from what the provider resends. An exact
    retry still gets the duplicate receipt (not 503 forever), without offering it to the hook again;
    a changed payload under the same delivery id is still refused."""
    import json

    from aiohttp.test_utils import TestClient, TestServer

    fired = []
    _rewriting_hook(fired)
    adapter, app = _webhook_app()
    async with TestClient(TestServer(app)) as client:
        authority = adapter._message_handler.__self__.session_authority
        assert (await _post_webhook(client, "please rewrite", "d-1")).status == 202
        retry = await _post_webhook(client, "please rewrite", "d-1")
        assert (retry.status, (await retry.json())["status"]) == (200, "duplicate")
        assert (await _post_webhook(client, "please rewrite it twice", "d-1")).status == 503
        rows = authority.db._read_all("SELECT payload_json FROM session_admissions")
    assert [json.loads(row["payload_json"])["text"] for row in rows] == ["rewritten"]
    assert fired == ["d-1"]


@pytest.mark.asyncio
async def test_a_webhook_row_committed_before_the_fingerprint_retries_exactly_and_runs_without_the_hook():
    """Upgrade: a row committed before ingress fingerprints (every main-era row: the original payload,
    no hook at ingress) keeps exact retry comparison, and when it executes after the upgrade the hook
    does not fire: the committed text runs as admitted."""
    import json

    from aiohttp.test_utils import TestClient, TestServer

    from gateway.session_contract import SessionRef
    from tests.waiting import async_wait_until

    fired = []
    adapter, app = _webhook_app()
    async with TestClient(TestServer(app)) as client:
        runner = adapter._message_handler.__self__
        authority = runner.session_authority
        runner._handle_message_with_agent = AsyncMock(return_value="agent-ok")
        assert (await _post_webhook(client, "please rewrite", "d-old")).status == 202
        _rewriting_hook(fired)  # the plugin arrives with the upgrade
        retry = await _post_webhook(client, "please rewrite", "d-old")
        assert (retry.status, (await retry.json())["status"]) == (200, "duplicate")
        assert (await _post_webhook(client, "please rewrite it twice", "d-old")).status == 503
        [row] = authority.db._read_all("SELECT target_session_id, payload_json FROM session_admissions")
        assert "ingress_sha256" not in json.loads(row["payload_json"])["native_text_v1"]

        del authority._schedule  # the queued row now runs on the real drain
        authority._schedule(SessionRef(authority.profile_id, row["target_session_id"]))
        await async_wait_until(lambda: authority.db._read_all("SELECT 1 FROM session_admissions WHERE status='terminal'"),
                               what="the queued row executed")
        executed = [call.args[0].text for call in runner._handle_message_with_agent.await_args_list]
    assert executed == ["please rewrite"]
    assert fired == []



@pytest.mark.asyncio
async def test_an_identical_webhook_delivery_waits_for_the_running_hook_and_gets_its_receipt(monkeypatch):
    """Overlapping identical deliveries (a provider retry while the first request is still in the hook)
    are coordinated by delivery identity: the second waits, rechecks the ledger, and resolves to the
    committed receipt, so the hook and its external actions run once and one row is committed."""
    import asyncio
    import json

    from aiohttp.test_utils import TestClient, TestServer

    import gateway.platforms.webhook_ingress as ingress
    from hermes_cli.plugins import get_plugin_manager
    from tests.waiting import async_wait_until

    fired, release, entered = [], asyncio.Event(), []

    async def hook(event, **_kwargs):
        fired.append(event.message_id)
        await release.wait()
        return {"action": "rewrite", "text": "rewritten"}

    manager = get_plugin_manager()
    manager._discovered = True
    manager._hooks.setdefault("pre_gateway_dispatch", []).append(hook)
    admit = ingress.admit_producer

    async def observed(adapter, event):
        entered.append(event.message_id)
        return await admit(adapter, event)

    monkeypatch.setattr(ingress, "admit_producer", observed)
    adapter, app = _webhook_app()
    async with TestClient(TestServer(app)) as client:
        authority = adapter._message_handler.__self__.session_authority
        first = asyncio.create_task(_post_webhook(client, "please rewrite", "d-1"))
        await async_wait_until(lambda: fired, what="the first delivery in the hook")
        second = asyncio.create_task(_post_webhook(client, "please rewrite", "d-1"))
        parked = lambda: any(waiting > 1 for _lock, waiting in getattr(ingress, "_deliveries", {}).values())
        await async_wait_until(lambda: len(entered) == 2 and (len(fired) > 1 or parked()),
                               what="the identical delivery parked or in the hook")
        release.set()
        first, second = await asyncio.gather(first, second)
        assert first.status == 202
        assert (second.status, (await second.json())["status"]) == (200, "duplicate")
        rows = authority.db._read_all("SELECT payload_json FROM session_admissions")
    assert [json.loads(row["payload_json"])["text"] for row in rows] == ["rewritten"]
    assert fired == ["d-1"]


