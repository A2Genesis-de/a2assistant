"""request_elevation / elevation_status / pre_tool_call as the plugin registers them, driven through a
fake approver: approved, denied, timed out, unavailable, admin sudo hand-off and grant expiry."""

import json
from types import SimpleNamespace

import pytest

from tests.plugins.a2_elevation.conftest import load

plugin = load()
approval = load("approval")
elevation = load("elevation")
grants = load("grants")
Outcome = approval.Outcome


class FakeApprover:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def ask(self, request):
        self.requests.append(request)
        return self.result


class SudoRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, password, ttl_seconds):
        self.calls.append((password, ttl_seconds))


class FakeContext:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.telegram_factories = []
        self.cli_commands = {}

    def register_tool(self, name, toolset, schema, handler, emoji=""):
        self.tools[name] = (toolset, schema, handler)

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_telegram_handler(self, factory):
        self.telegram_factories.append(factory)

    def register_cli_command(self, name, help, setup_fn, handler_fn):
        self.cli_commands[name] = (setup_fn, handler_fn)


@pytest.fixture
def sudo():
    return SudoRecorder()


@pytest.fixture
def make_plugin(store, sudo):
    def build(result):
        approver = FakeApprover(result)
        ctx = FakeContext()
        plugin.install(ctx, elevation.ElevationService(store, approver, sudo), load("telegram_bridge").TelegramBridge())
        return ctx, approver

    return build


def _call(ctx, tool, **args):
    return json.loads(ctx.tools[tool][2](args))


def _hook(ctx, tool_name, **args):
    return ctx.hooks["pre_tool_call"](tool_name=tool_name, args=args)


def test_registers_tools_hook_telegram_wiring_and_cli(make_plugin):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.DENIED, "mac"))

    assert set(ctx.tools) == {"request_elevation", "elevation_status"}
    assert {toolset for toolset, _, _ in ctx.tools.values()} == {"a2_elevation"}
    assert "pre_tool_call" in ctx.hooks
    assert len(ctx.telegram_factories) == 1
    assert "elevation" in ctx.cli_commands


def test_protected_call_is_blocked_until_granted(make_plugin):
    ctx, approver = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "telegram", actor="Joel"))

    blocked = _hook(ctx, "terminal", command="ssh a2-server uptime")
    assert blocked["action"] == "block"
    assert "request_elevation" in blocked["message"] and "scope='protected'" in blocked["message"]

    granted = _call(ctx, "request_elevation", reason="Logs prüfen", scope="protected")

    assert granted == {"status": "granted", "scope": "protected", "channel": "telegram", "seconds_left": 600}
    assert _hook(ctx, "terminal", command="ssh a2-server uptime") is None
    assert approver.requests[0].needs_password is False


def test_unprotected_and_own_tools_are_never_blocked(make_plugin):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.DENIED, "mac"))

    assert _hook(ctx, "terminal", command="git status") is None
    assert _hook(ctx, "request_elevation", reason="sudo", scope="admin") is None
    assert _hook(ctx, "elevation_status") is None


def test_protected_grant_does_not_cover_sudo(make_plugin):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac"))
    _call(ctx, "request_elevation", reason="Schlüssel", scope="protected")

    blocked = _hook(ctx, "terminal", command="sudo pfctl -sr")

    assert blocked["action"] == "block" and "scope='admin'" in blocked["message"]


def test_admin_grant_hands_the_password_to_sudo_for_the_grant_lifetime(make_plugin, sudo):
    ctx, approver = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac", password="pw"))

    granted = _call(ctx, "request_elevation", reason="pf-Regeln", scope="admin")

    assert granted["status"] == "granted"
    assert approver.requests[0].needs_password is True
    assert sudo.calls == [("pw", grants.GRANT_SECONDS)]
    assert _hook(ctx, "terminal", command="sudo pfctl -sr") is None
    assert _hook(ctx, "read_file", path="~/Admin/keys/x") is None


def test_grant_expiry_blocks_again(make_plugin, clock):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac"))
    _call(ctx, "request_elevation", reason="Schlüssel", scope="protected")

    clock.advance(grants.GRANT_SECONDS)

    assert _hook(ctx, "read_file", path="~/Admin/keys/x")["action"] == "block"
    assert _call(ctx, "elevation_status") == {"active": False}


@pytest.mark.parametrize(("outcome", "fragment"), [
    (Outcome.DENIED, "abgelehnt"),
    (Outcome.TIMED_OUT, "Keine Antwort innerhalb von 2 Minuten"),
    (Outcome.FAILED, "falsches Passwort"),
    (Outcome.UNAVAILABLE, "war erreichbar"),
])
def test_refusals_grant_nothing_and_are_audited(make_plugin, sudo, tmp_path, outcome, fragment):
    ctx, _ = make_plugin(approval.ApprovalResult(outcome, "mac"))

    result = _call(ctx, "request_elevation", reason="sudo nötig", scope="admin")

    assert result["status"] == outcome.value
    assert fragment in result["message"]
    assert sudo.calls == []
    assert _hook(ctx, "terminal", command="sudo true")["action"] == "block"
    (entry,) = [json.loads(line) for line in (tmp_path / "elevation" / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert (entry["event"], entry["channel"]) == (outcome.value, "mac")


def test_existing_grant_is_reused_without_asking(make_plugin, clock):
    ctx, approver = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac", password="pw"))
    _call(ctx, "request_elevation", reason="erst", scope="admin")
    clock.advance(100)

    again = _call(ctx, "request_elevation", reason="noch mal", scope="protected")

    assert again == {"status": "already_granted", "scope": "admin", "seconds_left": 500}
    assert len(approver.requests) == 1


@pytest.mark.parametrize("args", [{"reason": "x", "scope": "root"}, {"reason": "  ", "scope": "protected"}, {}])
def test_invalid_requests_are_tool_errors(make_plugin, args):
    ctx, approver = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac"))

    result = _call(ctx, "request_elevation", **args)

    assert "error" in result
    assert approver.requests == []


def test_status_reports_scope_channel_and_time_left(make_plugin, clock):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "telegram"))
    _call(ctx, "request_elevation", reason="Deploy", scope="protected")
    clock.advance(60)

    assert _call(ctx, "elevation_status") == {
        "active": True, "scope": "protected", "reason": "Deploy", "channel": "telegram", "seconds_left": 540,
    }


def test_cli_revoke_ends_the_grant_and_drops_the_sudo_password(make_plugin, sudo, capsys):
    ctx, _ = make_plugin(approval.ApprovalResult(Outcome.APPROVED, "mac", password="pw"))
    _call(ctx, "request_elevation", reason="pf", scope="admin")
    _, handler = ctx.cli_commands["elevation"]

    handler(SimpleNamespace(action="revoke"))

    assert json.loads(capsys.readouterr().out) == {"active": False}
    assert sudo.calls[-1] == ("", 0)
    assert _hook(ctx, "terminal", command="sudo true")["action"] == "block"
