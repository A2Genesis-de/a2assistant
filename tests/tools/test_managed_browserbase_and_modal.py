import os
import sys
import threading
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_cli.nous_account import NousPortalAccountInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"


def _load_tool_module(module_name: str, filename: str):
    spec = spec_from_file_location(module_name, TOOLS_DIR / filename)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _reset_modules(prefixes: tuple[str, ...]):
    for name in list(sys.modules):
        if name.startswith(prefixes):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _restore_tool_and_agent_modules():
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tools"
        or name.startswith("tools.")
        or name == "agent"
        or name.startswith("agent.")
    }
    try:
        yield
    finally:
        _reset_modules(("tools", "agent"))
        sys.modules.update(original_modules)


@pytest.fixture(autouse=True)
def _enable_managed_nous_tools(monkeypatch):
    """Ensure managed_nous_tools_enabled() returns True even after module reloads.

    The _install_fake_tools_package() helper resets and reimports tool modules,
    so a simple monkeypatch on tool_backend_helpers doesn't survive.  We patch
    the *source* modules that the reimported modules will import from — both
    hermes_cli.nous_account — so the function body returns True.
    """
    monkeypatch.setattr(
        "hermes_cli.nous_account.get_nous_portal_account_info",
        lambda: NousPortalAccountInfo(
            logged_in=True,
            source="jwt",
            fresh=False,
            paid_service_access=True,
        ),
    )


def _install_fake_tools_package():
    _reset_modules(("tools", "agent"))

    tools_package = types.ModuleType("tools")
    tools_package.__path__ = [str(TOOLS_DIR)]  # type: ignore[attr-defined]
    sys.modules["tools"] = tools_package

    env_package = types.ModuleType("tools.environments")
    env_package.__path__ = [str(TOOLS_DIR / "environments")]  # type: ignore[attr-defined]
    sys.modules["tools.environments"] = env_package

    agent_package = types.ModuleType("agent")
    agent_package.__path__ = [str(REPO_ROOT / "agent")]  # type: ignore[attr-defined]
    sys.modules["agent"] = agent_package
    sys.modules["agent.auxiliary_client"] = types.SimpleNamespace(
        call_llm=lambda *args, **kwargs: "",
    )
    # Keep unrelated imports real; only replace the collaborators this fixture
    # isolates. tools.browser_tool imports redact_cdp_url;
    # hermes_cli.auth (imported transitively by nous_account /
    # tool_backend_helpers) imports sanitize_borrowed_credential_payload.
    sys.modules["agent.redact"] = types.SimpleNamespace(
        redact_cdp_url=lambda value: str(value),
    )
    sys.modules["agent.credential_persistence"] = types.SimpleNamespace(
        sanitize_borrowed_credential_payload=lambda entry, provider_id=None: entry,
    )

    class _StubBrowserProvider:
        """Minimal BrowserProvider stub for ``from agent.browser_provider import BrowserProvider``."""

    sys.modules["agent.browser_provider"] = types.SimpleNamespace(
        BrowserProvider=_StubBrowserProvider,
    )
    sys.modules["agent.browser_registry"] = types.SimpleNamespace(
        get_provider=lambda name: None,
        list_providers=list,
        register_provider=lambda provider: None,
    )

    plugins_package = types.ModuleType("plugins")
    plugins_package.__path__ = []  # type: ignore[attr-defined]
    sys.modules["plugins"] = plugins_package

    sys.modules["tools.managed_tool_gateway"] = _load_tool_module(
        "tools.managed_tool_gateway",
        "managed_tool_gateway.py",
    )

    interrupt_event = threading.Event()
    sys.modules["tools.interrupt"] = types.SimpleNamespace(
        set_interrupt=lambda value=True: interrupt_event.set() if value else interrupt_event.clear(),
        is_interrupted=lambda: interrupt_event.is_set(),
        _interrupt_event=interrupt_event,
    )
    sys.modules["tools.approval"] = types.SimpleNamespace(
        detect_dangerous_command=lambda *args, **kwargs: None,
        check_dangerous_command=lambda *args, **kwargs: {"approved": True},
        check_all_command_guards=lambda *args, **kwargs: {"approved": True},
        load_permanent_allowlist=lambda *args, **kwargs: [],
        DANGEROUS_PATTERNS=[],
    )

    class _Registry:
        def register(self, **kwargs):
            return None

    from tools.registry import tool_error

    sys.modules["tools.registry"] = types.SimpleNamespace(
        registry=_Registry(), tool_error=tool_error,
    )

    class _DummyEnvironment:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def cleanup(self):
            return None

    class _DummyConnectionError(Exception):
        def __init__(self, message="", backend="", detail="", *args):
            super().__init__(message, *args)
            self.backend = backend
            self.detail = detail

    sys.modules["tools.environments.base"] = types.SimpleNamespace(
        BaseEnvironment=_DummyEnvironment,
        EnvironmentConnectionError=_DummyConnectionError,
    )
    sys.modules["tools.environments.local"] = types.SimpleNamespace(LocalEnvironment=_DummyEnvironment)
    sys.modules["tools.environments.ssh"] = types.SimpleNamespace(SSHEnvironment=_DummyEnvironment)
    sys.modules["tools.environments.docker"] = types.SimpleNamespace(DockerEnvironment=_DummyEnvironment)


def test_browser_explicit_local_mode_stays_local_even_when_managed_gateway_is_ready(tmp_path):
    _install_fake_tools_package()
    (tmp_path / "config.yaml").write_text("browser:\n  cloud_provider: local\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "HERMES_HOME": str(tmp_path),
        "TOOL_GATEWAY_USER_TOKEN": "nous-token",
    })

    with patch.dict(os.environ, env, clear=True):
        browser_config = _load_tool_module("tools.browser_config", "browser_config.py")

        provider = browser_config.get_cloud_provider()
        local_backend = browser_config.is_local_backend()

    assert provider is None
    assert local_backend is True  # no SSRF guard: the browser really is this host's


class TestShellEscapeBypass:
    """Regression for #36846/#36847: backslash escapes and empty-string
    literals split tokens so a denylisted command (rm) slips past detection
    while the shell still executes it."""

    def test_backslash_escape_bypass_caught(self):
        from tools.approval import detect_dangerous_command
        # literal: r-backslash-m -rf /  (shell collapses r\m -> rm)
        assert detect_dangerous_command("r\\m -rf /")[0] is True

    def test_empty_string_literal_bypass_caught(self):
        from tools.approval import detect_dangerous_command
        assert detect_dangerous_command("r''m -rf /")[0] is True
        assert detect_dangerous_command('r""m -rf /')[0] is True

    def test_plain_dangerous_still_caught(self):
        from tools.approval import detect_dangerous_command
        assert detect_dangerous_command("rm -rf /")[0] is True

    def test_benign_command_not_flagged(self):
        from tools.approval import detect_dangerous_command
        assert detect_dangerous_command("ls -la")[0] is False
