import logging
import platform
import time
from typing import Any, Optional

from tools.registry import tool_error, tool_result

from .grants import GRANT_SECONDS, GrantStore
from .policy import SCOPE_ADMIN, SCOPE_PROTECTED, required_scope
from .prompt import DialogOutcome, PasswordDialog

logger = logging.getLogger(__name__)

REQUEST_TOOL = "request_elevation"
STATUS_TOOL = "elevation_status"
TOOLSET = "a2_elevation"

SCOPE_LABELS = {
    SCOPE_PROTECTED: "Geschützte Daten und Systeme (Schlüssel, Schlüsselbund, Produktionsserver, a2-denise)",
    SCOPE_ADMIN: "Administratorrechte (sudo) und alle geschützten Bereiche",
}

OUTCOME_MESSAGES = {
    DialogOutcome.DENIED: "Joel hat die Freigabe abgelehnt. Nicht erneut fragen, sondern anders vorgehen oder nachfragen.",
    DialogOutcome.TIMED_OUT: "Keine Antwort am Mac innerhalb von 2 Minuten. Später erneut fragen oder Joel informieren.",
    DialogOutcome.FAILED: "Dreimal falsches Passwort. Freigabe verweigert.",
    DialogOutcome.UNAVAILABLE: "Der Freigabe-Dialog konnte nicht angezeigt werden.",
}

REQUEST_SCHEMA = {
    "name": REQUEST_TOOL,
    "description": (
        "Ask Joel for a time-limited grant to protected resources. A native macOS dialog on his Mac shows the "
        "reason; he confirms with his password. The grant lasts 10 minutes, then expires automatically. Scope "
        "'protected' covers ~/Admin/keys, the keychain, production servers and a2-denise; scope 'admin' also allows "
        "sudo. Call it only when a blocked tool call told you to, with a short concrete German reason."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Short German reason shown in the dialog."},
            "scope": {"type": "string", "enum": [SCOPE_PROTECTED, SCOPE_ADMIN]},
        },
        "required": ["reason", "scope"],
        "additionalProperties": False,
    },
}

STATUS_SCHEMA = {
    "name": STATUS_TOOL,
    "description": "Show whether a protected-resource grant is active, its scope and seconds left.",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

store = GrantStore()
dialog = PasswordDialog()


def _blocked_message(scope: str, label: str) -> str:
    return (
        f"Geschützt: {label}. Rufe zuerst {REQUEST_TOOL} mit scope='{scope}' und einer kurzen Begründung auf. "
        "Joel bestätigt am Mac mit seinem Passwort, danach gilt die Freigabe 10 Minuten."
    )


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **_: Any) -> Optional[dict[str, str]]:
    if tool_name in (REQUEST_TOOL, STATUS_TOOL):
        return None
    rule = required_scope(tool_name, args)
    if rule is None:
        return None
    grant = store.current()
    if grant and grant.covers(rule.scope, time.time()):
        return None
    return {"action": "block", "message": _blocked_message(rule.scope, rule.label)}


def _handle_request(args: dict, **_: Any) -> str:
    scope = str(args.get("scope") or "")
    reason = str(args.get("reason") or "").strip()
    if scope not in SCOPE_LABELS:
        return tool_error(f"scope must be one of {sorted(SCOPE_LABELS)}")
    if not reason:
        return tool_error("reason is required")
    now = time.time()
    existing = store.current()
    if existing and existing.covers(scope, now):
        return tool_result(status="already_granted", scope=existing.scope, seconds_left=existing.seconds_left(now))
    result = dialog.ask(reason, SCOPE_LABELS[scope], with_password=scope == SCOPE_ADMIN)
    if result.outcome is not DialogOutcome.APPROVED:
        store.audit(result.outcome.value, scope, reason)
        if result.detail:
            logger.warning("a2-elevation dialog: %s", result.detail)
        return tool_result(status=result.outcome.value, message=OUTCOME_MESSAGES[result.outcome])
    grant = store.grant(scope, reason)
    if scope == SCOPE_ADMIN:
        from tools.terminal_tool_sudo import set_elevated_sudo_password
        set_elevated_sudo_password(result.password, GRANT_SECONDS)
    return tool_result(status="granted", scope=grant.scope, seconds_left=GRANT_SECONDS)


def _handle_status(args: dict, **_: Any) -> str:
    now = time.time()
    grant = store.current()
    if grant is None:
        return tool_result(active=False)
    return tool_result(active=True, scope=grant.scope, reason=grant.reason, seconds_left=grant.seconds_left(now))


def register(ctx) -> None:
    if platform.system() != "Darwin":
        logger.info("a2-elevation: macOS only, not registering")
        return
    ctx.register_tool(name=REQUEST_TOOL, toolset=TOOLSET, schema=REQUEST_SCHEMA, handler=_handle_request, emoji="🔐")
    ctx.register_tool(name=STATUS_TOOL, toolset=TOOLSET, schema=STATUS_SCHEMA, handler=_handle_status, emoji="🔐")
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
