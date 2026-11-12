"""MacDialogApprover: maps the Swift helper's exit codes, returns the password only when asked, and kills
the dialog when another channel answered first."""

import os
import subprocess
import threading
from pathlib import Path

import pytest

from tests.plugins.a2_elevation.conftest import load

mac_dialog = load("mac_dialog")
approval = load("approval")
texts = load("texts")
Outcome = approval.Outcome


class FakeHelper:
    def __init__(self, error=None):
        self._error = error

    def path(self):
        if self._error is not None:
            raise self._error
        return Path("/fake/a2-elevate")


class FakeProcess:
    """Finishes with ``returncode`` once ``finish`` is set; ``kill`` ends it as SIGKILL would."""

    def __init__(self, returncode=None, stdout="", stderr=""):
        self.returncode = None
        self._final = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.finish = threading.Event()
        if returncode is not None:
            self.finish.set()
        self.killed = False

    def communicate(self, timeout=None):
        if not self.finish.wait(timeout):
            raise subprocess.TimeoutExpired("a2-elevate", timeout)
        self.returncode = self._final
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class Launcher:
    def __init__(self, process):
        self.process = process
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return self.process


def _request(needs_password=False, timeout_seconds=120.0):
    return approval.ApprovalRequest(reason="Signierschlüssel lesen", scope="protected",
                                    scope_label="Geschützte Daten", needs_password=needs_password,
                                    timeout_seconds=timeout_seconds)


def _approver(process, helper=None, clock=None):
    launcher = Launcher(process)
    kwargs = {"clock": clock} if clock else {}
    return mac_dialog.MacDialogApprover(helper or FakeHelper(), launch=launcher, **kwargs), launcher


@pytest.mark.parametrize(("code", "outcome"), [
    (0, Outcome.APPROVED), (2, Outcome.DENIED), (3, Outcome.TIMED_OUT), (4, Outcome.FAILED), (9, Outcome.UNAVAILABLE),
])
def test_exit_codes_map_to_outcomes(code, outcome):
    approver, _ = _approver(FakeProcess(code, stderr="detail"))

    result = approver.ask(_request(), threading.Event())

    assert (result.outcome, result.channel) == (outcome, "mac")


def test_password_is_returned_only_for_password_requests():
    with_password, launcher = _approver(FakeProcess(0, stdout="s3cret"))
    without_password, plain_launcher = _approver(FakeProcess(0, stdout="s3cret"))

    assert with_password.ask(_request(needs_password=True), threading.Event()).password == "s3cret"
    assert without_password.ask(_request(), threading.Event()).password == ""
    assert "--print-password" in launcher.commands[0]
    assert "--print-password" not in plain_launcher.commands[0]


def test_dialog_shows_the_texts_and_the_app_icon():
    approver, launcher = _approver(FakeProcess(2))

    approver.ask(_request(), threading.Event())

    arguments = dict(zip(launcher.commands[0][1::2], launcher.commands[0][2::2]))
    assert arguments["--title"] == texts.REQUEST_TITLE
    assert arguments["--details"].startswith("Signierschlüssel lesen\n\nBereich: Geschützte Daten")
    assert (arguments["--approve"], arguments["--deny"]) == ("Freigeben", "Ablehnen")
    assert arguments["--app"].endswith(".app") and arguments["--app"].startswith("/Applications/")
    assert arguments["--timeout"] == "120"


def test_another_channel_winning_kills_the_dialog():
    process = FakeProcess()
    approver, _ = _approver(process)
    stop = threading.Event()
    stop.set()

    result = approver.ask(_request(), stop)

    assert result.outcome is Outcome.SUPERSEDED
    assert process.killed


def test_hung_dialog_is_killed_after_its_deadline():
    process = FakeProcess()
    ticks = iter([0.0, 1000.0])
    approver, _ = _approver(process, clock=lambda: next(ticks))

    result = approver.ask(_request(timeout_seconds=1), threading.Event())

    assert result.outcome is Outcome.TIMED_OUT
    assert process.killed


@pytest.mark.parametrize("error", [OSError("swiftc missing"), subprocess.CalledProcessError(1, "swiftc")])
def test_unbuildable_helper_is_unavailable(error):
    approver, launcher = _approver(FakeProcess(0), helper=FakeHelper(error))

    result = approver.ask(_request(), threading.Event())

    assert result.outcome is Outcome.UNAVAILABLE
    assert launcher.commands == []


def test_up_to_date_helper_is_not_rebuilt(tmp_path):
    source = tmp_path / "a2_elevate.swift"
    binary = tmp_path / "bin" / "a2-elevate"
    source.write_text("", encoding="utf-8")
    binary.parent.mkdir()
    binary.write_text("", encoding="utf-8")
    os.utime(binary, (source.stat().st_mtime + 10, source.stat().st_mtime + 10))

    assert mac_dialog.SwiftHelper(binary, source).path() == binary
