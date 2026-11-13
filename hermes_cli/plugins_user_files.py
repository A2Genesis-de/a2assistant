"""User-owned files inside an installed plugin tree, carried across a forced reinstall."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from pm.filesystem import is_junction

_PRESERVE_SKIP = ("__pycache__", ".git", ".hermes-catalog.json")
_NO_GIT_REVISION_FILES = frozenset({
    "plugin.yaml", "plugin.yml", "plugin.json", "mcp.json",
    "pyproject.toml", "package.json", "package-lock.json", "uv.lock",
})
_NO_GIT_REVISION_DIRS = frozenset({"dashboard", "desktop", "skills", "sidecar", "node_modules"})
_NO_GIT_REVISION_EXTENSIONS = frozenset({".mjs", ".cjs", ".jsx", ".tsx"})


def _skip_preserve(name: str) -> bool:
    """Installer/cache names that are never user state (checked per path component)."""
    return name in _PRESERVE_SKIP or name.endswith(".pyc")


def _revision_owned_without_git(rel: Path) -> bool:
    """True for plugin code/control surfaces an update must never resurrect from the old tree."""
    from tools.plugin_guard import CODE_FILE_EXTENSIONS
    suffix = rel.suffix.lower()
    return (
        suffix in CODE_FILE_EXTENSIONS
        or suffix in _NO_GIT_REVISION_EXTENSIONS
        or rel.as_posix() in _NO_GIT_REVISION_FILES
        or bool(rel.parts and rel.parts[0] in _NO_GIT_REVISION_DIRS)
    )


def local_changes(target: Path) -> tuple[Optional[list[str]], list[str]]:
    """``(untracked_or_ignored, modified_tracked)`` in a git checkout. The first item is ``None``
    when git cannot classify the installed tree (notably subdirectory installs, which carry no ``.git``)."""
    from hermes_cli.plugins_cmd import PluginOperationError, _resolve_git_executable, _run_plugin_git
    git_exe = _resolve_git_executable()
    if not (target / ".git").exists():
        return None, []
    if not git_exe:
        raise PluginOperationError(
            f"Could not inspect local changes for '{target.name}': git executable is unavailable."
        )
    status = _run_plugin_git(git_exe, target, "status", "--porcelain", "--ignored", "-z", "--untracked-files=all",
                             "--ignored=matching", timeout=30)
    if status.returncode != 0:
        detail = (status.stderr or status.stdout or "git status failed").strip()
        raise PluginOperationError(
            f"Could not inspect local changes for '{target.name}': {detail}"
        )
    local, modified = [], []
    for item in status.stdout.split("\0"):
        if len(item) < 4:
            continue
        code, rel = item[:2], item[3:]
        if any(_skip_preserve(part) for part in Path(rel).parts):
            continue
        (local if code in ("??", "!!") else modified).append(rel)
    return local, modified


def stash_local_files(target: Path, rels: list[str], stash: Path) -> None:
    for rel in rels:
        src = target / rel
        if src.is_file():
            dst = stash / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def carry_user_files(old: Path, new: Path, local: Optional[list[str]]) -> list[str]:
    """Carry user-owned files into a staged replacement without reviving old plugin code.

    For a git checkout, *local* is the ``??``/``!!`` set and may contain a directory entry
    such as ``data/``; descendants of those entries are copied and win over same-path files in
    the new tree. ``None`` means there is no git checkout, so user-state files absent from the new
    tree are carried while executable/declarative plugin surfaces remain revision-owned. If a
    user-owned path cannot be represented safely in the new tree (a layout clash, or a symlink in a
    git checkout's untracked/ignored set), fail before publication rather than silently dropping it.
    Dirs in ``tools.plugin_guard.EXCLUDED_DIRS`` (``.venv/``, ``node_modules/``, tool caches) are
    install artefacts: they are neither carried nor inspected, so links inside them never stop an update.
    Returns the carried paths (POSIX, relative to the tree) so a later scan block can name them.
    """
    from hermes_cli.plugins_cmd import PluginOperationError
    from tools.plugin_guard import EXCLUDED_DIRS

    keep = {Path(rel) for rel in local or ()}
    linked: list[str] = []
    carried: list[str] = []

    def _user_link(rel: Path) -> None:
        if local is not None and not keep.isdisjoint((rel, *rel.parents)):
            linked.append(rel.as_posix())

    def _walk_error(exc: OSError) -> None:
        raise PluginOperationError(f"Could not preserve user files from '{old}': {exc}") from exc

    def _conflict(rel: Path, reason: str = "its destination conflicts with the updated plugin") -> PluginOperationError:
        return PluginOperationError(
            f"Cannot preserve user file '{rel}': {reason}. The installed plugin was left unchanged."
        )

    for dirpath, dirnames, filenames in os.walk(old, onerror=_walk_error):
        here = Path(dirpath)
        walk = []
        for name in dirnames:
            if (_skip_preserve(name) or name in EXCLUDED_DIRS
                    or (local is None and here == old and name in _NO_GIT_REVISION_DIRS)):
                continue
            if (here / name).is_symlink() or is_junction(here / name):
                _user_link((here / name).relative_to(old))
                continue
            walk.append(name)
        dirnames[:] = walk
        for name in filenames:
            if _skip_preserve(name):
                continue
            src = here / name
            rel = src.relative_to(old)
            if local is None:
                if _revision_owned_without_git(rel):
                    continue
            elif keep.isdisjoint((rel, *rel.parents)):
                continue
            try:
                src_mode = src.lstat().st_mode
            except OSError as exc:
                raise PluginOperationError(f"Could not preserve user file '{rel}': {exc}") from exc
            if stat.S_ISLNK(src_mode):
                _user_link(rel)
                continue
            if not stat.S_ISREG(src_mode):
                continue

            dst = new / rel
            if os.path.lexists(dst):
                if is_junction(dst):
                    raise _conflict(rel)
                if dst.is_dir() and not dst.is_symlink():
                    raise _conflict(rel, "the updated plugin now has a directory at that path")
                if local is None:
                    continue

            parent = new
            source_parent = old
            for part in rel.parent.parts:
                parent /= part
                source_parent /= part
                if os.path.lexists(parent):
                    if is_junction(parent) or parent.is_symlink() or not parent.is_dir():
                        raise _conflict(rel)
                    continue
                try:
                    source_info = source_parent.lstat()
                    if is_junction(source_parent) or not stat.S_ISDIR(source_info.st_mode):
                        raise _conflict(rel, "its source path changed during the update")
                    mode = stat.S_IMODE(source_info.st_mode)
                    parent.mkdir(mode=mode)
                    parent.chmod(mode)
                except PluginOperationError:
                    raise
                except OSError as exc:
                    raise _conflict(rel, "its destination could not be prepared") from exc
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            shutil.copy2(src, dst, follow_symlinks=False)
            carried.append(rel.as_posix())
    if linked:
        raise PluginOperationError(
            f"Cannot preserve symlinked user file(s) {', '.join(sorted(linked))}: links are not followed "
            "into an update. Replace each with a regular file (or remove it) and retry. "
            "The installed plugin was left unchanged."
        )
    return carried
