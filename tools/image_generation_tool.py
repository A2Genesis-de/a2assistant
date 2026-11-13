#!/usr/bin/env python3
"""``image_generate``: dispatches to the image gen provider plugin selected by ``image_gen.provider``
(``plugins/image_gen/<name>/``) and renders the tool schema from that provider's capabilities."""

import json
import logging
import os
from typing import Any, Optional

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO, VALID_ASPECT_RATIOS

logger = logging.getLogger(__name__)


# --- Config readers ---
def _read_image_gen_key(key: str) -> Optional[str]:
    """Return the stripped ``image_gen.<key>`` string from config.yaml, or None."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        value = section.get(key) if isinstance(section, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as exc:
        logger.debug("Could not read image_gen.%s: %s", key, exc)
    return None


def _read_configured_image_model():
    """``image_gen.model`` from config.yaml, or None."""
    return _read_image_gen_key("model")


def _read_configured_image_provider():
    """``image_gen.provider`` from config.yaml, or None (no image backend selected)."""
    return _read_image_gen_key("provider")


# --- Artifact path hinting for non-local terminal backends ---
_CONTAINER_HOME_ENVS = {"DockerEnvironment"}
# No env yet: only deterministic cache roots translate side-effect free (SSH: tilde path; its
# first sync uploads the cache file).
_CACHE_BASE_BY_BACKEND = {"docker": "/root/.hermes", "ssh": "~/.hermes"}


def _looks_like_absolute_file_path(value: str) -> bool:
    if not value or not isinstance(value, str) or value.lower().startswith(("http://", "https://", "data:")):
        return False
    return os.path.isabs(value) or (len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"})


def _active_terminal_env(task_id: str | None):
    try:
        from tools.terminal_tool_lifecycle import get_active_env
        return get_active_env(task_id or "default")
    except Exception as exc:
        logger.debug("Could not inspect active terminal environment: %s", exc)
        return None


def _agent_cache_base_for_env(env: Any) -> str | None:
    if env is not None:
        # Optional extension hook: an environment may expose its own agent-visible cache root.
        explicit = getattr(env, "agent_visible_cache_base", None)
        if callable(explicit):
            try:
                value = explicit()
                if value:
                    return str(value).rstrip("/")
            except Exception as exc:
                logger.debug("active env agent_visible_cache_base failed: %s", exc)
        remote_home = getattr(env, "_remote_home", None)
        if remote_home:
            return f"{str(remote_home).rstrip('/')}/.hermes"
        if env.__class__.__name__ in _CONTAINER_HOME_ENVS:
            return "/root/.hermes"
    from tools.terminal_scope import terminal_env
    backend = (terminal_env("TERMINAL_ENV") or "local").strip().lower()
    return _CACHE_BASE_BY_BACKEND.get(backend)


def _postprocess_image_generate_result(raw: str, task_id: str | None = None) -> str:
    """Annotate successful local results: ``image`` stays the host/gateway-deliverable path;
    ``agent_visible_image`` is the same file as seen by a non-local terminal backend."""
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return raw
    if not isinstance(payload, dict) or not payload.get("success"):
        return raw
    image = payload.get("image")
    if not isinstance(image, str) or not _looks_like_absolute_file_path(image):
        return raw
    env = _active_terminal_env(task_id)
    cache_base = _agent_cache_base_for_env(env)
    if not cache_base:
        return raw
    try:
        from tools.credential_files import map_cache_path_to_container
        agent_path = map_cache_path_to_container(image, container_base=cache_base)
    except Exception as exc:
        logger.debug("Could not translate image cache path for backend: %s", exc)
        return raw
    if not agent_path or agent_path == image:
        return raw
    sync_manager = getattr(env, "_sync_manager", None)
    if sync_manager is not None:
        try:
            sync_manager.sync(force=True)
        except Exception as exc:
            logger.warning("Could not force-sync generated image artifact: %s", exc)
    payload.setdefault("host_image", image)
    payload.setdefault("agent_visible_image", agent_path)
    return json.dumps(payload, ensure_ascii=False)


def _get_plugin_provider(name: str, *, force: bool = False):
    """Discover plugins (local import: importing this module must not trigger discovery) and return the named provider."""
    from agent.image_gen_registry import get_provider
    from hermes_cli.plugins import _ensure_plugins_discovered
    if force:
        _ensure_plugins_discovered(force=True)
    else:
        _ensure_plugins_discovered()
    return get_provider(name)


def check_image_generation_requirements() -> bool:
    """True if the configured image gen provider is registered and available."""
    configured = _read_configured_image_provider()
    if configured is None:
        return False
    provider = _get_plugin_provider(configured)
    return bool(provider and provider.is_available())


# --- Registry ---
from tools.registry import registry, tool_error

IMAGE_GENERATE_SCHEMA = {
    "name": "image_generate",
    # Placeholder: description AND params are rebuilt at get_tool_definitions() time by
    # _build_dynamic_image_schema() from the active backend's capabilities. Edit-only args
    # and upscale are advertised ONLY when supported; the handler accepts them regardless
    # (replay compat + teaching errors).
    "description": (
        "Generate or edit images with the configured model. Edit/reference "
        "capabilities are rendered at serving time."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "The text prompt describing the desired image (text-to-"
                    "image) or the edit to apply (image-to-image). Be detailed "
                    "and descriptive."
                ),
            },
            "aspect_ratio": {
                "type": "string",
                "enum": list(VALID_ASPECT_RATIOS),
                "description": "The aspect ratio of the generated image. 'landscape' is 16:9 wide, 'portrait' is 16:9 tall, 'square' is 1:1.",
                "default": DEFAULT_ASPECT_RATIO,
            },
            # image_url / reference_image_urls / upscale are added per-capability; never statically.
        },
        # See #95681.
        "required": ["prompt"],
    },
}


# --- Plugin provider dispatch ---
def _provider_error(error: str, error_type: str) -> str:
    """JSON error envelope shared by every provider-dispatch failure path."""
    return json.dumps({"success": False, "image": None, "error": error, "error_type": error_type})


def _provider_result(result, contract_error: str) -> str:
    """JSON-encode a provider's dict result; anything else is a contract violation."""
    if not isinstance(result, dict):
        return _provider_error(contract_error, "provider_contract")
    return json.dumps(result)


def _add_provider_kwargs(kwargs, image_url, reference_image_urls, upscale, model=None, controls=None) -> dict[str, Any]:
    """Add the optional ``provider.generate(**kwargs)`` args in place (edit args only when supplied)."""
    if model:
        kwargs["model"] = model
    if controls:
        kwargs.update(controls)
    if isinstance(image_url, str) and image_url.strip():
        kwargs["image_url"] = image_url.strip()
    if reference_image_urls is not None:
        from agent.image_gen_provider import normalize_reference_images
        norm_refs = normalize_reference_images(reference_image_urls)
        if norm_refs:
            kwargs["reference_image_urls"] = norm_refs
    if upscale is not None:
        kwargs["upscale"] = bool(upscale)
    return kwargs


def _declared_controls(provider, controls: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The subset of ``controls`` that ``provider`` declares in ``creative_controls``.

    A model can still send a control the current schema no longer offers (it copies earlier turns
    after the backend changed), and a third-party ``generate()`` without ``**kwargs`` would raise."""
    if not controls:
        return None
    try:
        declared = (provider.capabilities() or {}).get("creative_controls") or ()
    except Exception:
        return None
    return {name: value for name, value in controls.items() if name in declared} or None


def _dispatch_to_plugin_provider(
    prompt: str, aspect_ratio: str, image_url: Optional[str] = None,
    reference_image_urls: Optional[list] = None, upscale: Optional[bool] = None,
    controls: Optional[dict[str, Any]] = None):
    """JSON result from the selected plugin provider. Providers without ``upscale`` ignore it via ``**kwargs``."""
    configured = _read_configured_image_provider()
    if configured is None:
        return _provider_error(
            "Image generation has no backend: set image_gen.provider via `hermes tools` → Image Generation "
            "(run `hermes plugins list` to see installed backends).", "provider_not_configured")
    try:
        provider = _get_plugin_provider(configured)
    except Exception as exc:
        logger.debug("image_gen plugin lookup failed: %s", exc)
        provider = None
    if provider is None:
        # Long-lived sessions may have discovered plugins before a bundled backend
        # was patched in or config changed: retry once with a forced refresh.
        try:
            provider = _get_plugin_provider(configured, force=True)
        except Exception as exc:
            logger.debug("image_gen plugin force-refresh skipped: %s", exc)
    if provider is None:
        return _provider_error(
            f"image_gen.provider='{configured}' is set but no plugin registered that name. "
            f"Run `hermes plugins list` to see available image gen backends.", "provider_not_registered")
    pname = getattr(provider, "name", "?")
    kwargs: dict[str, Any] = {"prompt": prompt, "aspect_ratio": aspect_ratio}
    try:
        _add_provider_kwargs(kwargs, image_url, reference_image_urls, upscale,
                             model=_read_configured_image_model(), controls=_declared_controls(provider, controls))
        result = provider.generate(**kwargs)
    except Exception as exc:
        # A TypeError from generate() predating image_url support (third-party plugin not yet
        # updated): text-to-image keeps working; surface a clear note when an edit was requested.
        is_type_error = isinstance(exc, TypeError)
        if is_type_error and ("image_url" in kwargs or "reference_image_urls" in kwargs):
            logger.warning("image_gen provider '%s' rejected image-to-image kwargs "
                           "(signature too narrow): %s", pname, exc)
            return _provider_error(
                f"Provider '{pname}' does not support image-to-image / editing (its generate() "
                f"signature is out of date with the image_generate schema). Omit image_url for "
                f"text-to-image, or pick a backend that supports editing via `hermes tools` → "
                f"Image Generation.", "modality_unsupported")
        logger.warning("Image gen provider '%s' raised%s: %s", pname,
                       " TypeError" if is_type_error else "", exc)
        return _provider_error(f"Provider '{pname}' error: {exc}", "provider_exception")
    return _provider_result(result, "Provider returned a non-dict result")


def _confine_source_images(image_url, reference_image_urls, task_id, *, permitted: tuple = ("image",)):
    """Resolve path-like sources to ``data:`` URLs under a non-local terminal backend.

    Routes through ``tools.image_source`` (in-sandbox exec-read, media-cache host reads,
    credential guard) so generation obeys the same confinement as vision. URLs/data: pass
    through; local backend is a no-op. Returns ``(image_url, reference_image_urls, error_json_or_None)``.
    """
    from tools.terminal_scope import terminal_env
    if (terminal_env("TERMINAL_ENV") or "local").strip().lower() in ("", "local"):
        return image_url, reference_image_urls, None
    from model_tools import _run_async
    from tools.image_source import ImageResolutionError, resolve_local_source_to_data_url

    def resolve(ref):
        return _run_async(resolve_local_source_to_data_url(ref, task_id, permitted=permitted))
    try:
        if isinstance(image_url, str) and image_url.strip():
            image_url = resolve(image_url)
        if isinstance(reference_image_urls, (list, tuple)):
            reference_image_urls = [resolve(r) if isinstance(r, str) else r for r in reference_image_urls]
    except ImageResolutionError as exc:
        return image_url, reference_image_urls, _provider_error(
            f"Could not read source image: {exc}", type(exc).__name__)
    return image_url, reference_image_urls, None


def _handle_image_generate(args, **kw):
    prompt = args.get("prompt", "")
    if not prompt:
        return tool_error("prompt is required for image generation")
    aspect_ratio = args.get("aspect_ratio", DEFAULT_ASPECT_RATIO)
    upscale = args.get("upscale")
    task_id = kw.get("task_id")
    # Confinement chokepoint BEFORE dispatch: the provider receives sandbox-confined bytes.
    image_url, reference_image_urls, confine_error = _confine_source_images(
        args.get("image_url"), args.get("reference_image_urls"), task_id)
    if confine_error is not None:
        return confine_error
    controls = {name: args[name] for name in _CREATIVE_CONTROL_PARAMS if name in args}
    raw = _dispatch_to_plugin_provider(
        prompt, aspect_ratio, image_url=image_url, reference_image_urls=reference_image_urls,
        upscale=upscale if isinstance(upscale, bool) else None, controls=controls or None)
    return _postprocess_image_generate_result(raw, task_id=task_id)


# --- Dynamic schema — reflect the active backend's image-to-image capability ---
# Advertising edit capability up front saves a wasted turn. Memoized by config.yaml mtime in
# model_tools.get_tool_definitions(), so it rebuilds on switch.
_NO_CAPABILITIES = {"modalities": ["text"], "max_reference_images": 0, "supports_upscale": False}


def _active_image_capabilities() -> dict[str, Any]:
    """Best-effort capabilities of the configured provider/model; never raises.

    Fail-closed: an undeclared capability (or no configured provider) is advertised as absent.
    """
    info: dict[str, Any] = dict(_NO_CAPABILITIES)
    plugin_name = _read_configured_image_provider()
    if not plugin_name:
        return info
    try:
        provider = _get_plugin_provider(plugin_name)
    except Exception:
        return info
    if provider is None:
        return info
    try:
        caps = provider.capabilities() or {}
    except Exception:
        caps = {}
    info["provider"] = provider.display_name
    info["model"] = _read_configured_image_model() or (provider.default_model() or "")
    if caps.get("modalities"):
        info["modalities"] = list(caps["modalities"])
    if caps.get("max_reference_images"):
        info["max_reference_images"] = int(caps["max_reference_images"])
    # Plugins opt in explicitly; absent = no upscale param.
    info["supports_upscale"] = bool(caps.get("supports_upscale"))
    if caps.get("creative_controls"):
        info["creative_controls"] = list(caps["creative_controls"])
    if caps.get("source_image_role") == "style":
        info["source_image_role"] = "style"
    return info


_IMAGE_URL_PARAM = {
    "type": "string",
    "description": (
        "Source image to edit/transform (image-to-image). A public URL or "
        "an absolute local file path from the conversation. Omit for "
        "text-to-image."
    ),
}

# Creative-control vocabulary; a provider advertises the names it honors
# via ``capabilities()["creative_controls"]`` and only those reach the schema and its ``generate()``.
_CREATIVE_CONTROL_PARAMS = {
    "creativity": {
        "type": "string", "enum": ["raw", "low", "medium", "high"],
        "description": "Prompt expansion: raw (none), low, medium or high.",
    },
    "thinking": {
        "type": "string", "enum": ["fast", "high"],
        "description": "How much the model plans before generating: fast (default) or high for complex multi-step edits.",
    },
    "resolution": {
        "type": "string", "enum": ["1K", "2K"],
        "description": "Output size: 1K (default) or 2K when small text or fine detail matters.",
    },
    "intensity": {
        "type": "integer", "minimum": -100, "maximum": 100,
        "description": "Style intensity, -100 muted to 100 highly stylized. 0 neutral.",
    },
    "complexity": {
        "type": "integer", "minimum": -100, "maximum": 100,
        "description": "Composition density, -100 minimal to 100 dense. 0 neutral.",
    },
    "movement": {
        "type": "integer", "minimum": -100, "maximum": 100,
        "description": "Motion in the scene, -100 static to 100 dynamic. 0 neutral.",
    },
}

_STYLE_PROMPT_PARAM = {
    "type": "string",
    "description": (
        "The subject and scene to generate. Be detailed and descriptive; "
        "reference images supply only the look."
    ),
}

_STYLE_IMAGE_URL_PARAM = {
    "type": "string",
    "description": (
        "Style reference: its look is copied, the image itself is not edited. "
        "A public URL or an absolute local file path. Describe the subject in "
        "the prompt. Omit for text-to-image."
    ),
}

_UPSCALE_PARAM = {
    "type": "boolean",
    "description": (
        "Post-generation high-resolution pass (~2x, extra cost/latency), "
        "off by default. A creative enhancer that can alter fine detail "
        "(rendered text, faces) — use only when resolution matters more "
        "than fidelity."
    ),
}


def _build_dynamic_image_schema() -> dict[str, Any]:
    """Render description AND params from the active model's capabilities; args it cannot
    honor are NOT advertised (the handler still accepts them for replay compat)."""
    base_desc = (
        "{lead} {edit_clause}Use this rather than calling image APIs or scripts directly. "
        "Returns the result in the `image` field — a URL or an absolute "
        "file path; reference it in your response using the current "
        "platform's file-delivery convention."
    )
    info = _active_image_capabilities()
    max_refs = int(info.get("max_reference_images") or 0)
    can_edit = "image" in set(info.get("modalities") or ["text"])
    static_props = IMAGE_GENERATE_SCHEMA["parameters"]["properties"]
    properties: dict[str, Any] = {
        "prompt": static_props["prompt"], "aspect_ratio": static_props["aspect_ratio"]}
    style_refs = info.get("source_image_role") == "style"
    if can_edit:
        if style_refs:
            lead = "Generate images, optionally styled on reference images, via configured model."
            edit_clause = "Pass style references in image_url. "
            properties["prompt"] = _STYLE_PROMPT_PARAM
            properties["image_url"] = _STYLE_IMAGE_URL_PARAM
            refs_desc = f"Up to {max_refs} more style references. URLs or absolute local paths."
        else:
            lead = ("Generate or edit images (with reference images) using the configured model."
                    if max_refs > 1 else "Generate or edit images using the configured image model.")
            edit_clause = "Pass image_url to edit / transform an existing image. "
            properties["image_url"] = _IMAGE_URL_PARAM
            refs_desc = (
                f"Up to {max_refs} additional reference images (style, "
                "character, or composition) guiding an edit. URLs or "
                "absolute local paths."
            )
        if max_refs > 1:
            properties["reference_image_urls"] = {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": max_refs,
                "description": refs_desc,
            }
    else:
        lead = "Generate images from text with the configured model (it cannot edit images)."
        edit_clause = ""
    if info.get("supports_upscale"):
        properties["upscale"] = _UPSCALE_PARAM
    for name in info.get("creative_controls") or []:
        if name in _CREATIVE_CONTROL_PARAMS:
            properties[name] = _CREATIVE_CONTROL_PARAMS[name]
    return {"description": base_desc.format(lead=lead, edit_clause=edit_clause),
            "parameters": {"type": "object", "properties": properties, "required": ["prompt"]}}


registry.register(
    name="image_generate", toolset="image_gen", schema=IMAGE_GENERATE_SCHEMA,
    handler=_handle_image_generate, check_fn=check_image_generation_requirements, requires_env=[],
    is_async=False,
    emoji="🎨", dynamic_schema_overrides=_build_dynamic_image_schema,
)
