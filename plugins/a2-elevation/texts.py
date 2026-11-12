from hermes_cli.branding import PRODUCT_NAME

from .approval import APPROVAL_TIMEOUT_SECONDS, ApprovalRequest, ApprovalResult, Outcome
from .grants import GRANT_SECONDS
from .policy import SCOPE_ADMIN, SCOPE_PROTECTED

GRANT_MINUTES = GRANT_SECONDS // 60

SCOPE_LABELS = {
    SCOPE_PROTECTED: "Geschützte Daten und Systeme (Schlüssel, Schlüsselbund, Produktionsserver, a2-denise)",
    SCOPE_ADMIN: "Administratorrechte (sudo) und alle geschützten Bereiche",
}

REQUEST_TITLE = f"{PRODUCT_NAME} bittet um Freigabe"
APPROVE_LABEL = "Freigeben"
DENY_LABEL = "Ablehnen"
PASSWORD_PLACEHOLDER = "Passwort von {user}"
WRONG_PASSWORD = "Das Passwort war falsch."
SCOPE_LINE = "Bereich: {label}"
VALIDITY_LINE = f"Gilt {GRANT_MINUTES} Minuten und läuft dann automatisch ab."

AGENT_MESSAGES = {
    Outcome.DENIED: "Joel hat die Freigabe abgelehnt. Nicht erneut fragen, sondern anders vorgehen oder nachfragen.",
    Outcome.TIMED_OUT: (
        f"Keine Antwort innerhalb von {int(APPROVAL_TIMEOUT_SECONDS // 60)} Minuten. "
        "Später erneut fragen oder Joel informieren."
    ),
    Outcome.FAILED: "Dreimal falsches Passwort. Freigabe verweigert.",
    Outcome.UNAVAILABLE: "Weder der Freigabe-Dialog am Mac noch Telegram war erreichbar.",
}

CHANNEL_NAMES = {"mac": "am Mac", "telegram": "über Telegram"}

VERDICTS = {
    Outcome.APPROVED: "✅ Freigegeben",
    Outcome.DENIED: "❌ Abgelehnt",
    Outcome.FAILED: "❌ Abgelehnt (dreimal falsches Passwort)",
    Outcome.TIMED_OUT: "⌛ Abgelaufen, keine Antwort",
    Outcome.UNAVAILABLE: "⚠️ Nicht entschieden",
}

TOAST_UNAUTHORIZED = "Nicht berechtigt."
TOAST_ALREADY_DECIDED = "Bereits entschieden oder abgelaufen."
TOAST_APPROVED = "Freigegeben"
TOAST_DENIED = "Abgelehnt"


def blocked_message(scope: str, label: str, request_tool: str) -> str:
    return (
        f"Geschützt: {label}. Rufe zuerst {request_tool} mit scope='{scope}' und einer kurzen Begründung auf. "
        "Joel bestätigt am Mac mit seinem Passwort (geschützte Bereiche auch per Telegram), "
        f"danach gilt die Freigabe {GRANT_MINUTES} Minuten."
    )


def dialog_details(request: ApprovalRequest) -> str:
    return f"{request.reason}\n\n{SCOPE_LINE.format(label=request.scope_label)}\n{VALIDITY_LINE}"


def telegram_prompt(request: ApprovalRequest) -> str:
    return (
        f"🔐 {REQUEST_TITLE}: {request.reason} – gilt {GRANT_MINUTES} Minuten\n\n"
        f"{SCOPE_LINE.format(label=request.scope_label)}"
    )


def telegram_outcome(request: ApprovalRequest, final: ApprovalResult) -> str:
    verdict = VERDICTS.get(final.outcome, VERDICTS[Outcome.UNAVAILABLE])
    channel = CHANNEL_NAMES.get(final.channel, "")
    actor = f" von {final.actor}" if final.actor else ""
    headline = " ".join(part for part in (verdict, channel) if part) + actor
    return f"{headline}\n\n{request.reason}"
