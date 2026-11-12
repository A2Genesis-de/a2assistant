import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from hermes_constants import get_hermes_home

SOURCE = Path(__file__).with_name("a2_elevate.swift")
APP_ICON = "/Applications/A2Assistant.app/Contents/Resources/icon.icns"
DIALOG_TIMEOUT_SECONDS = 120


class DialogOutcome(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


EXIT_CODES = {0: DialogOutcome.APPROVED, 2: DialogOutcome.DENIED, 3: DialogOutcome.TIMED_OUT, 4: DialogOutcome.FAILED}


@dataclass(frozen=True)
class DialogResult:
    outcome: DialogOutcome
    password: str = ""
    detail: str = ""


class PasswordDialog:
    def __init__(self, binary: Path | None = None) -> None:
        self._binary = binary or get_hermes_home() / "elevation" / "bin" / "a2-elevate"

    def _ensure_binary(self) -> None:
        if self._binary.exists() and self._binary.stat().st_mtime >= SOURCE.stat().st_mtime:
            return
        self._binary.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        subprocess.run(
            ["/usr/bin/swiftc", "-O", str(SOURCE), "-o", str(self._binary)],
            check=True, capture_output=True, text=True, timeout=300,
        )

    def ask(self, reason: str, scope_label: str, *, with_password: bool) -> DialogResult:
        try:
            self._ensure_binary()
        except (OSError, subprocess.SubprocessError) as error:
            return DialogResult(DialogOutcome.UNAVAILABLE, detail=str(error))
        command = [
            str(self._binary), "--reason", reason, "--scope-label", scope_label,
            "--timeout", str(DIALOG_TIMEOUT_SECONDS), "--icon", APP_ICON,
        ]
        if with_password:
            command.append("--print-password")
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=DIALOG_TIMEOUT_SECONDS + 15, check=False,
            )
        except subprocess.TimeoutExpired:
            return DialogResult(DialogOutcome.TIMED_OUT)
        outcome = EXIT_CODES.get(completed.returncode, DialogOutcome.UNAVAILABLE)
        password = completed.stdout if outcome is DialogOutcome.APPROVED and with_password else ""
        return DialogResult(outcome, password=password, detail=completed.stderr.strip()[-300:])
