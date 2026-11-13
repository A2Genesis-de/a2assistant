"""Rate-limit and response-cache header capture for ``AIAgent``.

Parses provider response headers into ``_rate_limit_state`` (read by ``/usage``) and counts
OpenRouter response-cache hits. Every method resolves through ``AIAgent``'s MRO.
"""
import logging
from typing import Any

logger = logging.getLogger("run_agent")


def _response_headers(http_response: Any):
    return getattr(http_response, "headers", None) if http_response is not None else None


class RateLimitCaptureMixin:
    def _capture_rate_limits(self, http_response: Any) -> None:
        headers = _response_headers(http_response)
        if not headers:
            return
        try:
            from agent.rate_limit_tracker import parse_rate_limit_headers
            state = parse_rate_limit_headers(headers, provider=self.provider)
            if state is not None:
                self._rate_limit_state = state
        except Exception:
            pass

    def get_rate_limit_state(self):
        return self._rate_limit_state

    def _capture_anthropic_response_headers(self, http_response: Any) -> None:
        self._capture_rate_limits(http_response)

    def _check_openrouter_cache_status(self, http_response: Any) -> None:
        headers = _response_headers(http_response)
        if not headers:
            return
        try:
            status = headers.get("x-openrouter-cache-status")
            if not status:
                return
            if status.upper() == "HIT":
                self._or_cache_hits += 1
                logger.info("OpenRouter response cache HIT (total: %d)", self._or_cache_hits)
            else:
                logger.debug("OpenRouter response cache %s", status.upper())
        except Exception:
            pass
