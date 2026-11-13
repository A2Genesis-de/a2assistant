"""Tests for tools/fal_common.py — shared FAL.ai SDK plumbing.

Covers: import_fal_client.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from tools.fal_common import import_fal_client

# ---------------------------------------------------------------------------
# import_fal_client
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_fal_client(monkeypatch):
    module = types.ModuleType("fal_client")
    monkeypatch.setitem(sys.modules, "fal_client", module)
    return module

class TestImportFalClient:

    def test_pm_ensure_import_error_is_swallowed(self, monkeypatch, fake_fal_client):
        """If pm.ensure_import raises ImportError, the plain import decides."""
        monkeypatch.setattr(
            "pm.ensure_import",
            MagicMock(side_effect=ImportError("not installed")),
        )

        assert import_fal_client() is fake_fal_client

    def test_pm_ensure_other_exception_raises_import_error(self, monkeypatch):
        """A non-ImportError from pm (an install hint) surfaces as ImportError."""
        monkeypatch.setattr(
            "pm.ensure_import",
            MagicMock(side_effect=RuntimeError("install hint")),
        )
        with pytest.raises(ImportError, match="install hint"):
            import_fal_client()

    def test_pm_missing_is_swallowed(self, fake_fal_client):
        """If pm itself can't be imported, the plain import decides."""
        import builtins

        original_import = builtins.__import__

        def failing_import(name, *args, **kwargs):
            if name == "pm":
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            result = import_fal_client()
            assert result is fake_fal_client
