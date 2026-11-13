"""image_generate dynamic schema — capability-gated params (#95681 diet).

Contract: args the active provider cannot honor are NOT advertised. The plugin provider ABC's
capabilities() default fails closed to text-only/no-upscale, and no configured provider renders
the text-only schema.
"""
import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import tools.image_generation_tool as ig
from tools.image_generation_tool import IMAGE_GENERATE_SCHEMA, _build_dynamic_image_schema


class _Prov:
    display_name = "Fake Images"

    def __init__(self, caps):
        self._caps = caps

    def capabilities(self):
        return self._caps

    def default_model(self):
        return "img-1"


@contextmanager
def _active(caps):
    with patch.object(ig, "_read_configured_image_provider", return_value="fake"), \
         patch("agent.image_gen_registry.get_provider", return_value=_Prov(caps)), \
         patch("hermes_cli.plugins._ensure_plugins_discovered"):
        yield


def _schema_for(caps):
    with _active(caps):
        return _build_dynamic_image_schema()


_EDIT_CAPS = {"modalities": ["text", "image"], "max_reference_images": 4, "supports_upscale": True}


class TestProviderAbc(unittest.TestCase):
    def test_provider_abc_default_fails_closed(self):
        from agent.image_gen_provider import ImageGenProvider

        class _P(ImageGenProvider):
            name = "t"
            display_name = "T"
            def generate(self, prompt, aspect_ratio="landscape", **kw):
                return {}
            def list_models(self):
                return []
        caps = _P().capabilities()
        self.assertEqual(caps.get("modalities"), ["text"])
        self.assertFalse(caps.get("supports_upscale", False))


class TestDynamicParamGating(unittest.TestCase):
    def test_no_configured_provider_renders_text_only(self):
        with patch.object(ig, "_read_configured_image_provider", return_value=None):
            schema = _build_dynamic_image_schema()
        self.assertEqual(sorted(schema["parameters"]["properties"]), ["aspect_ratio", "prompt"])
        self.assertIn("cannot edit", schema["description"])

    def test_text_only_plugin_provider_hides_edit_and_upscale(self):
        schema = _schema_for({"modalities": ["text"], "max_reference_images": 0})
        props = schema["parameters"]["properties"]
        self.assertEqual(sorted(props), ["aspect_ratio", "prompt"])
        self.assertNotIn("upscale", props)

    def test_edit_provider_advertises_edit_args_with_cap(self):
        props = _schema_for(_EDIT_CAPS)["parameters"]["properties"]
        self.assertIs(props["image_url"], ig._IMAGE_URL_PARAM)
        self.assertEqual(props["reference_image_urls"]["maxItems"], 4)
        self.assertIn("edit", props["reference_image_urls"]["description"])
        self.assertIn("upscale", props)

    def test_creative_controls_follow_the_declared_names(self):
        props = _schema_for({**_EDIT_CAPS, "creative_controls": ["thinking", "unknown"]})["parameters"]["properties"]
        self.assertIn("thinking", props)
        self.assertNotIn("unknown", props)
        self.assertFalse({"creativity", "resolution"} & set(props))
        plain = _schema_for(_EDIT_CAPS)["parameters"]["properties"]
        self.assertFalse(set(ig._CREATIVE_CONTROL_PARAMS) & set(plain))

    def test_style_reference_backend_describes_image_inputs_as_style_not_edit(self):
        style = _schema_for({**_EDIT_CAPS, "source_image_role": "style"})["parameters"]["properties"]
        self.assertIs(style["image_url"], ig._STYLE_IMAGE_URL_PARAM)
        self.assertNotIn("edit", style["reference_image_urls"]["description"])
        self.assertNotIn("edit", style["prompt"]["description"])

    def test_static_schema_carries_no_capability_args(self):
        """The registration-time placeholder must stay minimal — dynamic
        overrides own the capability args (do-not-re-add guard)."""
        props = IMAGE_GENERATE_SCHEMA["parameters"]["properties"]
        self.assertEqual(sorted(props), ["aspect_ratio", "prompt"])


if __name__ == "__main__":
    unittest.main()
