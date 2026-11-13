"""Contract: media-send overrides must accept the ``metadata`` kwarg.

``BasePlatformAdapter.send_multiple_images`` passes ``metadata=metadata``
to ``send_image`` / ``send_image_file`` / ``send_animation`` on every send.
An override whose signature stops at ``reply_to`` raises ``TypeError:
send_image() got an unexpected keyword argument 'metadata'`` at runtime —
which is how image delivery broke on adapters in the past.
"""

from __future__ import annotations

import importlib
import inspect

import pytest


def _accepts_metadata(method) -> bool:
    params = inspect.signature(method).parameters
    if "metadata" in params:
        return True
    # A ``**kwargs`` catch-all also absorbs metadata.
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


# (module, class) for the bundled adapters. These must import in CI, so assert directly rather than skipping.
@pytest.mark.parametrize(
    "module_name, class_name",
    [
        ("plugins.platforms.telegram.adapter", "TelegramAdapter"),
    ],
)
def test_send_image_accepts_metadata(module_name, class_name):
    cls = getattr(importlib.import_module(module_name), class_name)
    assert _accepts_metadata(cls.send_image), (
        f"{class_name}.send_image must accept 'metadata' (or **kwargs) — "
        f"send_multiple_images passes it on every send"
    )
