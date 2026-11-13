"""/sethome env-var resolution: the platform's home-target env var and its thread companion."""

from gateway.run import _home_target_env_var, _home_thread_env_var


def test_telegram_home_target_env_var():
    assert _home_target_env_var("telegram") == "TELEGRAM_HOME_CHANNEL"


def test_home_thread_env_var_follows_the_target():
    assert _home_thread_env_var("telegram") == "TELEGRAM_HOME_CHANNEL_THREAD_ID"
