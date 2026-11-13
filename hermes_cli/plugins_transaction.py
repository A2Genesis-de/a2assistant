"""Publish plugin code and its dependency selection through one recoverable handoff."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def recover_plugin_publication(project: Path, row: dict, journal: Path) -> None:
    """Recover a shipped caller's row through the stdlib boot-journal owner."""
    from hermes_cli.runtime_state import _recover_plugin_publication

    _recover_plugin_publication(project, row, journal)


def publish_plugin(staged: Path, target: Path, old_metadata: dict, new_metadata: dict,
                   *, target_digest: str | None = None, require_consent: bool = False,
                   assume_consent: bool = False) -> None:
    """Publish *staged* into *target*. *assume_consent* is consent the caller
    already holds (``--yes-deps``, or a memory-provider migration under
    ``security.allow_lazy_installs``): the active-replacement consent veto is
    skipped, so an unattended install carries that decision instead of being
    refused non-interactively."""
    from pm.client import sync_venv
    from pm.plugin_inputs import StagedUpdate
    from pm.store import tree_digest

    if require_consent and not assume_consent:
        from hermes_cli import plugins_cmd
        from pm.workspace import enabled_plugin_dirs

        if target.resolve() in enabled_plugin_dirs(installing=target):
            consented, reason = plugins_cmd._install_plugin_python_deps(
                plugins_cmd._read_manifest_for_install(staged), staged, plugins_cmd._console())
            if not consented:
                outcome = ("Reinstall declined: {}. The installed plugin and active environment are unchanged."
                           if target.exists() else "Install declined: {}. Nothing was installed.")
                # The refusal carries its closed class (plugins_cmd_install._ConsentRefusal).
                from hermes_cli.observability.shared_metrics_fields import tagged_failure_class

                raise plugins_cmd.PluginOperationError(
                    outcome.format(reason), failure_class=tagged_failure_class(reason) or "other")

    sync_venv(explicit=True, plugins=StagedUpdate({
        "staged": str(staged.resolve()), "target": str(target.absolute()),
        "old_metadata": old_metadata, "new_metadata": new_metadata,
        "target_digest": target_digest if target_digest is not None else (tree_digest(target) if target.exists() else None),
    }))


def update_plugin(target: Path, **_options: Any) -> str:
    """Plugins are not updated in place; a forced reinstall from their source replaces them."""
    from hermes_cli.plugins_cmd import PluginOperationError

    raise PluginOperationError(
        f"Plugin '{target.name}' is not updated in place; reinstall it with `hermes plugins install --force`.")
