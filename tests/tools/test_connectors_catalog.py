"""``manage_catalog`` (catalog install through the connection card).

Contracts:
- the tool reaches only desktop sessions, whatever a config selects, and is deferred by default
- only a desktop chat draws it
- the model sends catalog ids and an action; every other key is refused before anything runs
"""

import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.connectors import live
from tools.connectors.catalog_tool import NOT_HERE, manage_catalog
from tools.connectors.contract import TargetState
from tools.connectors.run import apply_answer


@pytest.fixture(autouse=True)
def _clean_live():
    live.reset_for_tests()
    yield
    live.reset_for_tests()


class FakeInstaller:
    """The host side of a row: no skill resolves unless a subclass says so."""

    def __init__(self):
        self.installs = []

    def skill_meta(self, identifier):
        return None

    def install_skill(self, identifier, *, force):
        raise AssertionError("no skill in these tests")


def _card(answer, *, session_id="s1", profile_home=None):
    """A desktop card that answers the live operation a moment after it is drawn. ``profile_home`` is
    the session's profile, which ``connection.respond`` looks the operation up under."""
    seen = []

    def callback(payload):
        seen.append(payload)

        def respond():
            operation = live.get(session_id, payload["op_id"], profile_home=profile_home)
            if operation is not None:
                apply_answer(operation, json.dumps(answer(payload)))

        threading.Timer(0.01, respond).start()

    callback.seen = seen
    return callback


def _install(items, installer, card):
    with patch("tools.connectors.run.WATCH_INTERVAL_SECONDS", 0.01):
        return json.loads(manage_catalog({"action": "install", "items": items}, session_id="s1",
                                         connection_callback=card, card_surface=True, installer=installer))


def _approve(env=None):
    return lambda payload: {"targets": [{"name": t["name"], "status": "approved", "env": env}
                                        for t in payload["targets"] if t["state"] == "pending"]}


def test_only_a_desktop_session_carries_the_tool():
    import model_tools
    import toolsets
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from tools.tool_search import is_deferrable_tool_name

    # A config may name the toolset; `all` never brings it in.
    assert "manage_catalog" in model_tools._select_tool_names(["catalog", "web"], None, quiet_mode=True)
    assert "manage_catalog" not in model_tools._select_tool_names(None, None, quiet_mode=True)
    assert "manage_catalog" not in toolsets.resolve_toolset("all")
    # The agent's own session platform decides whether it keeps the tool.
    for platform in ("cli", "tui", "telegram", "cron", None):
        assert "manage_catalog" in toolsets.session_platform_tool_drops(platform), platform
    assert "manage_catalog" not in toolsets.session_platform_tool_drops("desktop")
    # Behind tool_search by default, like the other desktop surface tools.
    assert is_deferrable_tool_name("manage_catalog", frozenset(DEFAULT_CONFIG["tools"]["tool_search"]["defer"]))


def _desktop_child_toolsets():
    from tools.delegate_tool_toolsets import _resolve_child_toolsets
    parent = SimpleNamespace(enabled_toolsets=["catalog", "web"], disabled_toolsets=None)
    return _resolve_child_toolsets(parent, None, "leaf")


@pytest.mark.parametrize("platform", ["desktop", "cli", "subagent"])
def test_a_session_off_the_desktop_never_hears_of_the_tool_even_through_tool_search(monkeypatch, platform):
    """A CLI config naming ``catalog``, and a delegate child of a desktop chat, lose manage_catalog from
    the direct tools, the tool_search listing and the bridge's search, not just from the direct tools."""
    import model_tools
    from agent.agent_init import _load_tools

    monkeypatch.setattr("hermes_cli.plugins.discover_plugins", lambda: None)
    enabled, disabled = _desktop_child_toolsets() if platform == "subagent" else (["catalog", "web"], None)
    assert "catalog" in enabled
    agent = SimpleNamespace(quiet_mode=True, platform=platform, enabled_toolsets=enabled, disabled_toolsets=disabled)

    _load_tools(agent, enabled, disabled)
    found = json.loads(model_tools.handle_function_call(
        "tool_search", {"queries": ["catalog plugin install"]},
        enabled_toolsets=agent.enabled_toolsets, disabled_toolsets=agent.disabled_toolsets))

    carried = "manage_catalog" in json.dumps(agent.tools) or "manage_catalog" in json.dumps(found)
    assert carried is (platform == "desktop")


@pytest.mark.parametrize("args", [
    {"action": "install", "items": [{"kind": "skill", "id": "x"}], "profile": "work"},
    {"action": "install", "items": [{"kind": "skill", "id": "x", "sha": "b" * 40}]},
    {"action": "install", "items": [{"kind": "skill", "id": "x", "url": "https://evil.example/x"}]},
])
def test_a_source_version_or_profile_from_the_model_is_refused_before_anything_runs(args):
    installer, card = FakeInstaller(), _card(_approve())
    out = json.loads(manage_catalog(args, session_id="s1", connection_callback=card, card_surface=True,
                                    installer=installer))
    assert "error" in out and not card.seen and not installer.installs


def test_off_the_desktop_the_result_points_at_the_cli_and_opens_no_card():
    installer, card = FakeInstaller(), _card(_approve())
    for callback, surface in ((None, True), (card, False)):
        out = json.loads(manage_catalog({"action": "install", "items": [{"kind": "skill", "id": "x"}]},
                                        session_id="s1", connection_callback=callback, card_surface=surface,
                                        installer=installer))
        assert out["error"] == NOT_HERE
    assert not card.seen and not installer.installs and live.current("s1") is None
