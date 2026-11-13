"""Shared FAL.ai SDK plumbing: the lazy ``fal_client`` import and the queue result wait."""

from __future__ import annotations

from typing import Any

FAL_QUEUE_POLL_SECONDS = 2.0


def wait_fal_queue_result(handle: Any, *, interval: float = FAL_QUEUE_POLL_SECONDS) -> Any:
    """``handle.get()`` without the SDK's 0.1 s status poll: drain ``iter_events`` at ``interval``,
    then ``get()`` sees Completed on its first status check and fetches the result."""
    for _ in handle.iter_events(with_logs=False, interval=interval):
        pass
    return handle.get()


def import_fal_client() -> Any:
    """Import ``fal_client`` (via ``pm`` when available) and return
    the module reference.

    Callers cache the result on their own module global so tests can monkeypatch it.
    """
    try:
        from pm import ensure_import as _lazy_ensure
    except ImportError:
        # pm itself unavailable (externally-managed env, partial install) —
        # the plain import below is the authority on availability.
        pass
    else:
        try:
            _lazy_ensure("fal")
        except ImportError:
            pass  # same authority rule: let the plain import decide
        except Exception as exc:
            raise ImportError(str(exc))
    import fal_client  # type: ignore  # noqa: WPS433 — intentionally lazy
    return fal_client
