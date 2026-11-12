import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from hermes_cli.desktop_bundle import MACOS_APP_BUNDLE

from . import texts
from .approval import ApprovalRequest, ApprovalResult, Approver, Outcome

SOURCE = Path(__file__).with_name("a2_elevate.swift")
APP_PATH = Path("/Applications") / MACOS_APP_BUNDLE
PROCESS_GRACE_SECONDS = 15.0
POLL_SECONDS = 0.2
KILL_WAIT_SECONDS = 5.0

EXIT_CODES = {0: Outcome.APPROVED, 2: Outcome.DENIED, 3: Outcome.TIMED_OUT, 4: Outcome.FAILED}

Launcher = Callable[[list[str]], subprocess.Popen]


class SwiftHelper:
    def __init__(self, binary: Path, source: Path = SOURCE) -> None:
        self._binary = binary
        self._source = source

    def path(self) -> Path:
        if self._binary.exists() and self._binary.stat().st_mtime >= self._source.stat().st_mtime:
            return self._binary
        self._binary.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        subprocess.run(
            ["/usr/bin/swiftc", "-O", str(self._source), "-o", str(self._binary)],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=300, stdin=subprocess.DEVNULL,
        )
        return self._binary


def launch_dialog(command: list[str]) -> subprocess.Popen:
    pipe = subprocess.PIPE
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=pipe, stderr=pipe, text=True, encoding="utf-8")


def dialog_command(binary: Path, request: ApprovalRequest) -> list[str]:
    command = [
        str(binary),
        "--title", texts.REQUEST_TITLE,
        "--details", texts.dialog_details(request),
        "--approve", texts.APPROVE_LABEL,
        "--deny", texts.DENY_LABEL,
        "--placeholder", texts.PASSWORD_PLACEHOLDER,
        "--wrong-password", texts.WRONG_PASSWORD,
        "--timeout", str(int(request.timeout_seconds)),
        "--app", str(APP_PATH),
    ]
    if request.needs_password:
        command.append("--print-password")
    return command


class MacDialogApprover(Approver):
    channel = "mac"

    def __init__(self, helper: SwiftHelper, launch: Launcher = launch_dialog,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._helper = helper
        self._launch = launch
        self._clock = clock

    def ask(self, request: ApprovalRequest, stop: threading.Event) -> ApprovalResult:
        try:
            binary = self._helper.path()
            process = self._launch(dialog_command(binary, request))
        except (OSError, subprocess.SubprocessError) as error:
            return ApprovalResult(Outcome.UNAVAILABLE, self.channel, detail=str(error))
        deadline = self._clock() + request.timeout_seconds + PROCESS_GRACE_SECONDS
        while True:
            try:
                stdout, stderr = process.communicate(timeout=POLL_SECONDS)
            except subprocess.TimeoutExpired:
                if stop.is_set() or self._clock() >= deadline:
                    _terminate(process)
                    return ApprovalResult(Outcome.SUPERSEDED if stop.is_set() else Outcome.TIMED_OUT, self.channel)
                continue
            return self._result(process.returncode, stdout, stderr, request)

    def _result(self, returncode: int, stdout: str, stderr: str, request: ApprovalRequest) -> ApprovalResult:
        outcome = EXIT_CODES.get(returncode, Outcome.UNAVAILABLE)
        password = stdout if outcome is Outcome.APPROVED and request.needs_password else ""
        return ApprovalResult(outcome, self.channel, password=password, detail=(stderr or "").strip()[-300:])


def _terminate(process: subprocess.Popen) -> None:
    process.kill()
    process.wait(timeout=KILL_WAIT_SECONDS)
