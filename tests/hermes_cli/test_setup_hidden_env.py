"""Setup surfaces ask only for what a platform can't start without.

The knobs in SETUP_HIDDEN_ENV_SUFFIXES are self-configuring (/sethome) or
already correct by default, so they don't belong on a setup form. They must
still be reachable everywhere else — this is a presentation change, not a
feature removal.
"""


from hermes_cli.setup_hidden_env import is_setup_hidden_env


class TestIsSetupHiddenEnv:


    def test_applies_to_plugin_platforms_nobody_enumerated(self):
        """Suffix matching is the point — any plugin platform gets this for free."""
        for key in (
            "FAKECHAT_ALLOW_ALL_USERS",
            "FAKECHAT_HOME_CHANNEL",
            "FAKECHAT_HOME_CHANNEL_NAME",
        ):
            assert is_setup_hidden_env(key), key


class TestChannelCards:

    def test_no_card_shows_a_hidden_knob(self):
        from hermes_cli.web_server_messaging import _messaging_platform_catalog

        for entry in _messaging_platform_catalog():
            for key in entry["env_vars"]:
                assert not is_setup_hidden_env(key), f"{entry['id']}: {key}"


    def test_hidden_knobs_move_to_the_keys_page_not_into_a_void(self):
        """Keys hides what a Channels card owns. Dropping these from the card
        must hand them back to Keys, not orphan them from every surface."""
        from hermes_cli.web_server_messaging import _channel_managed_env_keys

        managed = _channel_managed_env_keys()
        for key in (
            "TELEGRAM_HOME_CHANNEL",
            "TELEGRAM_ALLOW_ALL_USERS",
            "TELEGRAM_REPLY_TO_MODE",
        ):
            assert key not in managed, f"{key} is hidden from both surfaces"


class TestStillConfigurable:
    def test_gateway_still_honors_the_env_vars(self, tmp_path, monkeypatch):
        """Nothing was removed from the product — only from the setup form."""
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:abcdefghijklmnop")
        monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")
        monkeypatch.setenv("TELEGRAM_REPLY_TO_MODE", "off")

        from gateway.config import Platform, load_gateway_config

        telegram = load_gateway_config().platforms[Platform.TELEGRAM]
        assert telegram.home_channel is not None
        assert telegram.home_channel.chat_id == "999"
        assert telegram.reply_to_mode == "off"
