"""A send the destination refused: terminal for the prompt, never retried as plain text."""

from typing import Any

SEND_DECLINE_CODE = "send_declined"


def declined_send(result: Any) -> bool:
    raw = getattr(result, "raw_response", None)
    return (isinstance(raw, dict) and not raw.get("success") and not raw.get("ambiguous")
            and raw.get("code") == SEND_DECLINE_CODE)
