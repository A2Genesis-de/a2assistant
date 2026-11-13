"""Tests for the image-to-image / editing surface of ``image_generate``.

The unified ``image_generate`` tool routes to a provider's edit endpoint when
``image_url`` / ``reference_image_urls`` is supplied, otherwise to text-to-image. Coverage:

- Plugin dispatch forwards image_url / reference_image_urls to ``generate()``
- ``capabilities()`` honesty drives the dynamic tool-schema description
- Providers whose ``generate()`` predates image inputs reject them with a clear error
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
import hermes_yaml as yaml

from agent import image_gen_registry
from agent.image_gen_provider import ImageGenProvider


@pytest.fixture(autouse=True)
def _reset_registry():
    image_gen_registry._reset_for_tests()
    yield
    image_gen_registry._reset_for_tests()


@pytest.fixture
def cfg_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _write_cfg(home, cfg: dict):
    (home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


# ---------------------------------------------------------------------------
# Plugin dispatch forwarding
# ---------------------------------------------------------------------------


class _EditCapableProvider(ImageGenProvider):
    def __init__(self):
        self.received: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "editcap"

    def capabilities(self) -> dict[str, Any]:
        return {"modalities": ["text", "image"], "max_reference_images": 4}

    def generate(self, prompt, aspect_ratio="landscape", *, image_url=None,
                 reference_image_urls=None, **kwargs):
        self.received = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_url": image_url,
            "reference_image_urls": reference_image_urls,
        }
        return {
            "success": True, "image": "/tmp/out.png", "model": "editcap-1",
            "prompt": prompt, "aspect_ratio": aspect_ratio,
            "modality": "image" if image_url else "text", "provider": "editcap",
        }


class _LegacyProvider(ImageGenProvider):
    """Provider whose generate() predates image_url (no **kwargs absorb)."""

    @property
    def name(self) -> str:
        return "legacy"

    def generate(self, prompt, aspect_ratio="landscape"):  # narrow signature
        return {"success": True, "image": "/tmp/legacy.png", "provider": "legacy"}


class TestPluginDispatchImageToImage:
    def test_dispatch_forwards_image_url(self, cfg_home, monkeypatch):
        import tools.image_generation_tool as image_tool
        from hermes_cli import plugins as plugins_module
        from agent import image_gen_registry as reg

        provider = _EditCapableProvider()
        reg.register_provider(provider)
        monkeypatch.setattr(image_tool, "_read_configured_image_provider", lambda: "editcap")
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda *a, **k: None)
        monkeypatch.setattr(reg, "get_provider", lambda n: provider if n == "editcap" else None)

        raw = image_tool._dispatch_to_plugin_provider(
            "make night", "square",
            image_url="https://in/src.png",
            reference_image_urls=["https://in/ref.png"],
        )
        out = json.loads(raw)
        assert out["success"] is True
        assert out["modality"] == "image"
        assert provider.received["image_url"] == "https://in/src.png"
        assert provider.received["reference_image_urls"] == ["https://in/ref.png"]


    def test_legacy_provider_edit_request_surfaces_clear_error(self, cfg_home, monkeypatch):
        import tools.image_generation_tool as image_tool
        from hermes_cli import plugins as plugins_module
        from agent import image_gen_registry as reg

        provider = _LegacyProvider()
        reg.register_provider(provider)
        monkeypatch.setattr(image_tool, "_read_configured_image_provider", lambda: "legacy")
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda *a, **k: None)
        monkeypatch.setattr(reg, "get_provider", lambda n: provider if n == "legacy" else None)

        raw = image_tool._dispatch_to_plugin_provider(
            "edit it", "square", image_url="https://in/src.png",
        )
        out = json.loads(raw)
        assert out["success"] is False
        assert out["error_type"] == "modality_unsupported"


# ---------------------------------------------------------------------------
# Dynamic schema reflects active capabilities
# ---------------------------------------------------------------------------


class TestDynamicSchema:
    def _no_discovery(self, monkeypatch):
        import hermes_cli.plugins as plugins_module
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda *a, **k: None)


    def test_builder_wired_into_registry(self):
        from tools.registry import discover_builtin_tools, registry

        discover_builtin_tools()
        entry = registry._tools["image_generate"]
        assert entry.dynamic_schema_overrides is not None
        out = entry.dynamic_schema_overrides()
        assert "description" in out
