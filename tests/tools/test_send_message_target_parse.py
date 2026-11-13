"""Parser-only and lightweight routing tests for send_message targets.

These stay separate from ``test_send_message_tool.py`` because that module
skips wholesale when optional Telegram dependencies are not installed.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.config import Platform
from tools.send_message_tool import _send_to_platform, send_message_tool
from tools.send_message_targets import _parse_target_ref


def _run_async_immediately(coro):
    return asyncio.run(coro)


def test_live_adapter_inherited_media_fallback_is_not_claimed_as_delivery(tmp_path) -> None:
    from gateway.platforms.base import BasePlatformAdapter, SendResult

    platform = Platform.WEBHOOK
    document = tmp_path / "report.txt"
    document.write_text("report", encoding="utf-8")

    class Adapter:
        name = "Fallback-only"
        send_document = BasePlatformAdapter.send_document

        async def send(self, **kwargs):
            return SendResult(success=True, message_id="warning-text-only")

    runner = SimpleNamespace(adapters={platform: Adapter()})
    with patch("gateway.run._gateway_runner_ref", return_value=runner):
        result = asyncio.run(
            _send_to_platform(
                platform,
                SimpleNamespace(enabled=True, token=None, extra={}),
                "31b543d5-80d4-4df5-8a5c-cefca1a58fdd",
                "attached",
                media_files=[(str(document), False)],
            )
        )

    assert "does not implement native document delivery" in result["error"]
    assert "media_delivered" not in result


def test_telegram_named_private_dm_topic_is_parsed() -> None:
    """``telegram:<positive_chat_id>:<topic_name>`` splits into chat + topic name (#80483);
    numeric topics keep their shape and a named topic on a group id stays unparsed."""
    assert _parse_target_ref("telegram", "722341991:Debug") == ("722341991", "Debug", True)
    assert _parse_target_ref("telegram", "722341991:17") == ("722341991", "17", True)
    assert _parse_target_ref("telegram", "-1001234567890:Debug") == (None, None, False)
    # Only the live cron router resolves the name; the REST sender (send_message, cron's
    # standalone fallback) must say so instead of failing on int("Debug").
    pconfig, bot = SimpleNamespace(token="token", extra={}), AsyncMock()
    with patch("plugins.platforms.telegram.standalone._telegram_bot", return_value=bot), \
            patch("plugins.platforms.telegram.standalone._telegram_format", return_value=("hi", None, False)):
        result = asyncio.run(_send_to_platform(Platform.TELEGRAM, pconfig, "722341991", "hi", thread_id="Debug"))
    assert "numeric thread id" in result["error"] and not bot.send_message.called


def test_resolved_opaque_plugin_target_uses_directory_id() -> None:
    from gateway.platform_registry import PlatformEntry, platform_registry

    platform_name = "opaque-resolved-test"
    entry = PlatformEntry(
        name=platform_name,
        label="Opaque resolved test",
        adapter_factory=lambda cfg: None,
        check_fn=lambda: True,
    )
    platform_registry.register(entry)
    platform = Platform(platform_name)
    pconfig = SimpleNamespace(enabled=True, token=None, extra={})
    config = SimpleNamespace(
        platforms={platform: pconfig},
        get_home_channel=lambda _platform: None,
    )
    try:
        with patch("gateway.config.load_gateway_config", return_value=config), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch(
                 "gateway.channel_directory.resolve_channel_name",
                 return_value="opaque:directory-id",
             ), \
             patch("model_tools._run_async", side_effect=_run_async_immediately), \
             patch(
                 "tools.send_message_tool._send_to_platform",
                 new=AsyncMock(return_value={"success": True}),
             ) as send_mock, \
             patch("gateway.mirror.mirror_to_session", return_value=True):
            result = json.loads(
                send_message_tool(
                    {
                        "action": "send",
                        "target": f"{platform_name}:Friendly name",
                        "message": "hello",
                    }
                )
            )
    finally:
        platform_registry.unregister(platform_name)

    assert result["success"] is True
    send_mock.assert_awaited_once_with(
        platform,
        pconfig,
        "opaque:directory-id",
        "hello",
        thread_id=None,
        media_files=[],
        force_document=False,
    )


def test_unresolved_plugin_target_requires_explicit_parser() -> None:
    from gateway.platform_registry import PlatformEntry, platform_registry

    platform_name = "opaque-verbatim-test"
    entry = PlatformEntry(
        name=platform_name,
        label="Opaque verbatim test",
        adapter_factory=lambda cfg: None,
        check_fn=lambda: True,
    )
    platform_registry.register(entry)
    platform = Platform(platform_name)
    # Simulate a fresh `hermes send` process: the dynamic Platform member
    # is known from config, but plugin discovery has not registered its
    # adapter entry yet.
    platform_registry.unregister(platform_name)
    pconfig = SimpleNamespace(enabled=True, token=None, extra={})
    config = SimpleNamespace(
        platforms={platform: pconfig},
        get_home_channel=lambda _platform: None,
    )
    try:
        with patch("gateway.config.load_gateway_config", return_value=config), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch(
                 "gateway.channel_directory.resolve_channel_name",
                 return_value=None,
             ), \
             patch(
                 "hermes_cli.plugins.discover_plugins",
                 side_effect=lambda: platform_registry.register(entry),
             ) as discover_mock, \
             patch("model_tools._run_async", side_effect=_run_async_immediately), \
             patch(
                 "tools.send_message_tool._send_to_platform",
                 new=AsyncMock(return_value={"success": True}),
             ) as send_mock, \
             patch("gateway.mirror.mirror_to_session", return_value=True):
            result = json.loads(
                send_message_tool(
                    {
                        "action": "send",
                        "target": f"{platform_name}:dm:panyaozhen",
                        "message": "hello",
                    }
                )
            )
    finally:
        platform_registry.unregister(platform_name)

    assert set(result) == {"error"}
    discover_mock.assert_called_once_with()
    send_mock.assert_not_awaited()


def test_unresolved_builtin_target_keeps_directory_error() -> None:
    telegram_cfg = SimpleNamespace(enabled=True, token="***", extra={})
    config = SimpleNamespace(
        platforms={Platform.TELEGRAM: telegram_cfg},
        get_home_channel=lambda _platform: None,
    )

    with patch("gateway.config.load_gateway_config", return_value=config), \
         patch("gateway.channel_directory.resolve_channel_name", return_value=None), \
         patch(
             "tools.send_message_tool._send_to_platform",
             new=AsyncMock(return_value={"success": True}),
         ) as send_mock:
        result = json.loads(
            send_message_tool(
                {
                    "action": "send",
                    "target": "telegram:missing-room",
                    "message": "hello",
                }
            )
        )

    assert set(result) == {"error"}
    assert "missing-room" in result["error"]
    send_mock.assert_not_awaited()



def test_unresolved_builtin_target_passes_through_when_requested() -> None:
    """Cron and react keep the old pass-through behavior for unresolved
    built-in targets: with no model in the loop to react to an error, the
    raw id must reach the adapter, as it did before resolve_send_target
    took over these callers."""
    from tools.send_message_tool import resolve_send_target

    with patch("gateway.channel_directory.resolve_channel_name", return_value=None):
        chat_id, thread_id, error = resolve_send_target(
            "telegram", "ops-room", pass_unresolved_references=True
        )

    assert error is None
    assert chat_id == "ops-room"
    assert thread_id is None




def test_parserless_plugin_target_passes_through_when_requested() -> None:
    """A plugin platform that declares no parser has no explicit syntax at
    all, so passing the raw id through is the only way cron can target it."""
    from gateway.platform_registry import PlatformEntry, platform_registry
    from tools.send_message_tool import resolve_send_target

    platform_name = "opaque-cron-fallback-test"
    entry = PlatformEntry(
        name=platform_name,
        label="Opaque cron fallback test",
        adapter_factory=lambda cfg: None,
        check_fn=lambda: True,
    )
    platform_registry.register(entry)
    try:
        with patch("gateway.channel_directory.resolve_channel_name", return_value=None):
            chat_id, thread_id, error = resolve_send_target(
                platform_name, "dm:panyaozhen", pass_unresolved_references=True
            )
    finally:
        platform_registry.unregister(platform_name)

    assert error is None
    assert chat_id == "dm:panyaozhen"
    assert thread_id is None


def test_plugin_parser_stays_authoritative_despite_fallback() -> None:
    """A plugin that DOES declare a parser stays strict for every caller:
    its parser is the authority on native syntax, so an unrecognized
    target errors even with pass_unresolved_references."""
    from gateway.platform_registry import PlatformEntry, platform_registry
    from tools.send_message_tool import resolve_send_target

    platform_name = "opaque-parser-strict-test"
    entry = PlatformEntry(
        name=platform_name,
        label="Opaque parser strict test",
        adapter_factory=lambda cfg: None,
        check_fn=lambda: True,
        parse_target_ref_fn=lambda ref: None,
    )
    platform_registry.register(entry)
    try:
        with patch("gateway.channel_directory.resolve_channel_name", return_value=None):
            chat_id, _thread_id, error = resolve_send_target(
                platform_name, "dm:panyaozhen", pass_unresolved_references=True
            )
    finally:
        platform_registry.unregister(platform_name)

    assert chat_id is None
    assert error is not None


def test_unknown_platform_that_left_core_names_its_install_command(tmp_path, monkeypatch):
    """A platform that moved out of core into a catalog plugin, sent to while the plugin is absent."""
    from gateway.config import GatewayConfig
    from tools.send_message_targets import resolve_send_target
    from tools.send_message_tool import _resolve_platform_config

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _, _, _, err = _resolve_platform_config("homeassistant", GatewayConfig())
    assert "unregistered plugin platform: homeassistant" in err and "`hermes plugins install homeassistant`" in err
    _, _, err = resolve_send_target("homeassistant", "living room")
    assert "`hermes plugins install homeassistant`" in err
    _, _, _, err = _resolve_platform_config("nosuchplatform", GatewayConfig())
    assert err == "Unknown or unregistered plugin platform: nosuchplatform"


def test_bare_platform_home_fallback_preserves_thread_id() -> None:
    telegram_cfg = SimpleNamespace(enabled=True, token="tok", extra={})
    home = SimpleNamespace(chat_id="12345", thread_id="777")
    config = SimpleNamespace(
        platforms={Platform.TELEGRAM: telegram_cfg},
        get_home_channel=lambda _platform: home,
    )

    with patch("gateway.config.load_gateway_config", return_value=config), \
         patch("tools.interrupt.is_interrupted", return_value=False), \
         patch("model_tools._run_async", side_effect=_run_async_immediately), \
         patch("tools.send_message_tool._send_to_platform", new=AsyncMock(return_value={"success": True})) as send_mock, \
         patch("gateway.mirror.mirror_to_session", return_value=True) as mirror_mock:
        result = json.loads(
            send_message_tool(
                {
                    "action": "send",
                    "target": "telegram",
                    "message": "hello topic",
                }
            )
        )

    assert result["success"] is True
    assert result["note"] == "Sent to telegram home channel (chat_id: 12345)"
    send_mock.assert_awaited_once_with(
        Platform.TELEGRAM,
        telegram_cfg,
        "12345",
        "hello topic",
        thread_id="777",
        media_files=[],
        force_document=False,
    )
    mirror_mock.assert_called_once_with(
        "telegram",
        "12345",
        "hello topic",
        source_label="cli",
        thread_id="777",
        user_id=None,
    )
