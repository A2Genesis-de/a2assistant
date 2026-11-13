"""Test helpers that pin whether the current activity is work for the local Desktop app."""

from contextvars import ContextVar


def as_local_desktop_backend(monkeypatch) -> None:
    from hermes_cli import process_identity
    monkeypatch.setattr(process_identity, "_SERVING_LOCAL_DESKTOP", ContextVar("serving_local_desktop_test", default=True))


def off_local_desktop(monkeypatch) -> None:
    from hermes_cli import process_identity
    monkeypatch.setattr(process_identity, "_SERVING_LOCAL_DESKTOP", ContextVar("serving_local_desktop_test", default=False))
