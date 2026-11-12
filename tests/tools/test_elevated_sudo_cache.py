"""The elevated sudo password (a2-elevation admin grant) is shared by every session and expires."""

from types import SimpleNamespace

import pytest

from tools import terminal_tool_sudo


@pytest.fixture
def monotonic(monkeypatch):
    clock = SimpleNamespace(now=500.0)
    monkeypatch.setattr(terminal_tool_sudo, "time", SimpleNamespace(monotonic=lambda: clock.now))
    terminal_tool_sudo._reset_cached_sudo_passwords()
    yield clock
    terminal_tool_sudo._reset_cached_sudo_passwords()


def test_elevated_password_serves_any_session_until_it_expires(monotonic):
    terminal_tool_sudo.set_elevated_sudo_password("pw", 600)

    monotonic.now += 599
    assert terminal_tool_sudo._get_cached_sudo_password() == "pw"

    monotonic.now += 1
    assert terminal_tool_sudo._get_cached_sudo_password() == ""


def test_empty_password_revokes_the_elevated_entry(monotonic):
    terminal_tool_sudo.set_elevated_sudo_password("pw", 600)

    terminal_tool_sudo.set_elevated_sudo_password("", 0)

    assert terminal_tool_sudo._get_cached_sudo_password() == ""


def test_session_password_wins_over_the_elevated_one(monotonic):
    terminal_tool_sudo.set_elevated_sudo_password("elevated", 600)
    terminal_tool_sudo._set_cached_sudo_password("own")

    assert terminal_tool_sudo._get_cached_sudo_password() == "own"

    monotonic.now += terminal_tool_sudo.SUDO_PASSWORD_TTL_SECONDS
    assert terminal_tool_sudo._get_cached_sudo_password() == ""
