"""Browser Use cloud browser provider: direct ``BROWSER_USE_API_KEY`` (https://browser-use.com).
Config: ``browser.cloud_provider: "browser-use"``."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent.secret_scope import get_secret
from plugins.browser._common import CloudBrowserProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.browser-use.com/api/v3"


class BrowserUseBrowserProvider(CloudBrowserProvider):
    """Browser Use (https://browser-use.com) cloud browser backend."""

    provider_id = "browser-use"
    label = "Browser Use"
    release_method = "patch"
    release_path = "/browsers/{session_id}"
    # Hidden from the picker; stays registered for legacy cloud_provider configs.
    setup_tag = None

    def is_available(self) -> bool:
        return bool(get_secret("BROWSER_USE_API_KEY"))

    def _get_config(self) -> dict[str, Any]:
        from tools.tool_backend_helpers import read_selection, selection_error

        api_key = get_secret("BROWSER_USE_API_KEY")
        if api_key:
            return {"api_key": api_key, "base_url": _BASE_URL}
        selected = read_selection("browser")
        if selected is not None:
            raise ValueError(selection_error("browser", selected, "BROWSER_USE_API_KEY is not set"))
        raise ValueError("Browser Use requires a direct BROWSER_USE_API_KEY credential.")

    def _headers(self, config: dict[str, Any]) -> dict[str, str]:
        return {"Content-Type": "application/json", "X-Browser-Use-API-Key": config["api_key"]}

    def _release_body(self, config: dict[str, Any]) -> dict[str, object]:
        return {"action": "stop"}

    def create_session(self, task_id: str) -> dict[str, object]:
        config = self._get_config()
        response = self._post_create(f"{config['base_url']}/browsers", self._headers(config), {}, wrap_errors=True)
        self._check_created(response)

        session_data = response.json()
        session_name = self._session_name(task_id)
        logger.info("Created Browser Use session %s", session_name)
        return {
            "session_name": session_name,
            "bb_session_id": session_data["id"],
            "cdp_url": session_data.get("cdpUrl") or session_data.get("connectUrl") or "",
            # Fixed server-side lifetime: keep the API's authority so an expired CDP endpoint is retired.
            "expires_at": session_data.get("timeoutAt"),
            "features": {"browser_use": True},
            "external_call_id": None,
        }
