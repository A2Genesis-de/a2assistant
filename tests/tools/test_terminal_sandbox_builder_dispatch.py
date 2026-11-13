"""Regression coverage for sandbox backend builder dispatch (#112715)."""

from tools import terminal_tool_backends as backends


def test_create_environment_keeps_env_type_for_plugin_backends(monkeypatch):
    """Unknown backends still receive their name for plugin provider lookup."""
    received = {}

    def build_plugin_env(**kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setattr(backends, "_build_plugin_env", build_plugin_env)

    backends._create_environment(
        env_type="plugin-sandbox",
        image="test-image",
        cwd="/workspace",
        timeout=42,
        container_config={},
        task_id="test-task",
    )

    assert received["env_type"] == "plugin-sandbox"
    assert received["image"] == "test-image"
