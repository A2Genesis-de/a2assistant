import re
from dataclasses import dataclass
from typing import Any

SCOPE_PROTECTED = "protected"
SCOPE_ADMIN = "admin"

PRODUCTION_HOSTS = ("a2-server", "kraftmatch-server", "babau-server", "gunna-server")


@dataclass(frozen=True)
class ProtectedRule:
    pattern: re.Pattern[str]
    scope: str
    label: str


RULES: tuple[ProtectedRule, ...] = (
    ProtectedRule(re.compile(r"(~|/Users/[^/\s]+)/Admin/keys"), SCOPE_PROTECTED, "Schlüsselordner ~/Admin/keys"),
    ProtectedRule(re.compile(r"Library/Keychains"), SCOPE_PROTECTED, "Schlüsselbund"),
    ProtectedRule(
        re.compile(r"\bsecurity\s+(find-(generic|internet)-password|dump-keychain|export|unlock-keychain)"),
        SCOPE_PROTECTED,
        "Schlüsselbund",
    ),
    ProtectedRule(
        re.compile(r"\b(ssh|scp|rsync|sftp)\b[^\n;|&]*\b(" + "|".join(PRODUCTION_HOSTS) + r")\b"),
        SCOPE_PROTECTED,
        "Produktionsserver",
    ),
    ProtectedRule(re.compile(r"\ba2-denise\b"), SCOPE_PROTECTED, "Gerät a2-denise"),
    ProtectedRule(re.compile(r"(^|[;&|(\s])sudo\b"), SCOPE_ADMIN, "Administratorrechte (sudo)"),
)

COMMAND_TOOLS = {"terminal": ("command",), "execute_code": ("code",)}
PATH_TOOLS = {"read_file", "write_file", "patch", "search_files"}
PATH_ARGS = ("path", "file_path", "paths", "target", "directory")


def _texts_to_scan(tool_name: str, args: Any) -> list[str]:
    if not isinstance(args, dict):
        return []
    if tool_name in COMMAND_TOOLS:
        return [str(args.get(key) or "") for key in COMMAND_TOOLS[tool_name]]
    if tool_name in PATH_TOOLS:
        values = [args.get(key) for key in PATH_ARGS]
        return [str(item) for value in values if value for item in (value if isinstance(value, list) else [value])]
    return []


def required_scope(tool_name: str, args: Any) -> ProtectedRule | None:
    for text in _texts_to_scan(tool_name, args):
        for rule in RULES:
            if rule.pattern.search(text):
                return rule
    return None
