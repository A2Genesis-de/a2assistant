import json
import logging
import platform
from typing import Any, Optional

from hermes_constants import get_hermes_home
from tools.registry import tool_error, tool_result

from . import texts
from .approval import FirstAnswerApprover
from .elevation import ElevationService, InvalidRequest
from .grants import GrantStore
from .mac_dialog import MacDialogApprover, SwiftHelper
from .policy import SCOPE_ADMIN, SCOPE_PROTECTED
from .telegram_bridge import TelegramApprover, TelegramBridge, handler_factory

logger = logging.getLogger(__name__)

REQUEST_TOOL = "request_elevation"
STATUS_TOOL = "elevation_status"
TOOLSET = "a2_elevation"
CLI_COMMAND = "elevation"

REQUEST_SCHEMA = {
    "name": REQUEST_TOOL,
    "description": (
        "Ask Joel for a time-limited grant to protected resources. A native macOS dialog on his Mac shows the "
        "reason; he confirms with his password. For scope 'protected' he can also approve from Telegram; the "
        "first answer wins. The grant lasts 10 minutes, then expires automatically. Scope 'protected' covers "
        "~/Admin/keys, the keychain, production servers and a2-denise; scope 'admin' also allows sudo and is "
        "only approved on the Mac. Call it only when a blocked tool call told you to, with a short concrete "
        "German reason."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Short German reason shown in the dialog and on Telegram."},
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


def _grant_sudo(password: str, ttl_seconds: float) -> None:
    from tools.terminal_tool_sudo import set_elevated_sudo_password

    set_elevated_sudo_password(password, ttl_seconds)


def build_service(bridge: TelegramBridge) -> ElevationService:
    directory = get_hermes_home() / "elevation"
    approver = FirstAnswerApprover([
        MacDialogApprover(SwiftHelper(directory / "bin" / "a2-elevate")),
        TelegramApprover(bridge),
    ])
    return ElevationService(GrantStore(directory), approver, _grant_sudo)


def _hook(service: ElevationService):
    def on_pre_tool_call(tool_name: str = "", args: Any = None, **_: Any) -> Optional[dict[str, str]]:
        if tool_name in (REQUEST_TOOL, STATUS_TOOL):
            return None
        rule = service.blocking_rule(tool_name, args)
        if rule is None:
            return None
        return {"action": "block", "message": texts.blocked_message(rule.scope, rule.label, REQUEST_TOOL)}

    return on_pre_tool_call


def _request_handler(service: ElevationService):
    def handle(args: dict, **_: Any) -> str:
        try:
            return tool_result(service.request(str(args.get("reason") or ""), str(args.get("scope") or "")))
        except InvalidRequest as error:
            return tool_error(str(error))

    return handle


def _status_handler(service: ElevationService):
    def handle(args: dict, **_: Any) -> str:
        return tool_result(service.status())

    return handle


def _cli_setup(parser: Any) -> None:
    parser.add_argument("action", choices=("status", "revoke"))


def _cli_handler(service: ElevationService):
    def handle(args: Any) -> int:
        if args.action == "revoke":
            service.revoke()
        print(json.dumps(service.status(), ensure_ascii=False))
        return 0

    return handle


def install(ctx: Any, service: ElevationService, bridge: TelegramBridge) -> None:
    ctx.register_tool(name=REQUEST_TOOL, toolset=TOOLSET, schema=REQUEST_SCHEMA,
                      handler=_request_handler(service), emoji="🔐")
    ctx.register_tool(name=STATUS_TOOL, toolset=TOOLSET, schema=STATUS_SCHEMA,
                      handler=_status_handler(service), emoji="🔐")
    ctx.register_hook("pre_tool_call", _hook(service))
    ctx.register_telegram_handler(handler_factory(bridge))
    ctx.register_cli_command(CLI_COMMAND, "Show or revoke the protected-resource grant",
                             _cli_setup, _cli_handler(service))


def register(ctx: Any) -> None:
    if platform.system() != "Darwin":
        logger.info("a2-elevation: macOS only, not registering")
        return
    bridge = TelegramBridge()
    install(ctx, build_service(bridge), bridge)
