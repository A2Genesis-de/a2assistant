"""Gateway plugins.manage install action."""

from unittest.mock import patch

from tui_gateway import server

def test_plugins_manage_install_missing_identifier():
    resp = server.handle_request(
        {
            "id": "1",
            "method": "plugins.manage",
            "params": {"action": "install"},
        }
    )

    assert "error" in resp

def test_plugins_manage_install_failure():
    with patch(
        "hermes_cli.plugins_cmd.dashboard_install_plugin",
        return_value={"ok": False, "error": "Git clone failed"},
    ):
        resp = server.handle_request(
            {
                "id": "1",
                "method": "plugins.manage",
                "params": {
                    "action": "install",
                    "identifier": "bad/repo",
                },
            }
        )

    assert "error" in resp
    assert "Git clone failed" in resp["error"]["message"]


def test_plugins_manage_list_reports_desktop_half(tmp_path):
    """A unified package (plugin.yaml + desktop/plugin.js) is reported with ``has_desktop_half`` so the
    desktop app can pair its app-level copy of that half with the agent row — one package, ONE row."""
    unified = tmp_path / "media"
    (unified / "desktop").mkdir(parents=True)
    (unified / "desktop" / "plugin.js").write_text("export default {}")
    agent_only = tmp_path / "snap"
    agent_only.mkdir()
    rows = [
        ("media", "1.0", "Media", "user", unified, "media"),
        ("snap", "1.0", "Snap", "user", agent_only, "snap"),
    ]
    with patch("hermes_cli.plugins_cmd._discover_all_plugins", return_value=rows), \
         patch("hermes_cli.plugins_cmd._get_enabled_set", return_value=set()), \
         patch("hermes_cli.plugins_cmd._get_disabled_set", return_value=set()):
        resp = server.handle_request({"id": "1", "method": "plugins.manage", "params": {"action": "list"}})

    by_name = {r["name"]: r for r in resp["result"]["plugins"]}
    assert by_name["media"]["has_desktop_half"] is True
    assert by_name["snap"]["has_desktop_half"] is False
    assert by_name["snap"]["servers"] == []

def test_plugins_manage_list_reports_a_root_layout_desktop_half(tmp_path):
    """A ROOT plugin.js beside plugin.yaml is a desktop half too (the install probe and the host's
    reconcile both read it), so the row pairs with its app-level copy like a ``desktop/`` one."""
    rooted = tmp_path / "radar"
    rooted.mkdir()
    (rooted / "plugin.js").write_text("export default {}")
    rows = [("radar", "1.0", "Radar", "user", rooted, "radar")]
    with patch("hermes_cli.plugins_cmd._discover_all_plugins", return_value=rows), \
         patch("hermes_cli.plugins_cmd._get_enabled_set", return_value=set()), \
         patch("hermes_cli.plugins_cmd._get_disabled_set", return_value=set()):
        resp = server.handle_request({"id": "1", "method": "plugins.manage", "params": {"action": "list"}})

    assert resp["result"]["plugins"][0]["has_desktop_half"] is True


