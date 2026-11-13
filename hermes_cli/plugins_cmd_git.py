"""Plugin install metadata (``.install-metadata.json`` source/revision/pin records) and the git plumbing
behind clone, exact-revision checkout, credential scrubbing and the autostashing ``git pull``.

Sibling of :mod:`hermes_cli.plugins_cmd` (the facade re-exports the names other modules use and is
imported late here, never at module level).
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional

from hermes_cli._subprocess_compat import noninteractive_git_env
from hermes_constants import get_hermes_home
from utils import atomic_write_text


def _pc():
    """The facade, read at call time: tests patch ``plugins_cmd.<name>`` and sibling calls must see it."""
    from hermes_cli import plugins_cmd
    return plugins_cmd


_EXACT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _install_metadata_path() -> Path:
    return get_hermes_home() / "plugins" / ".install-metadata.json"


def _read_install_metadata() -> dict[str, dict[str, object]]:
    """Read profile-local, non-secret plugin source metadata from disk."""
    path = _install_metadata_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _pc().PluginOperationError(f"Could not read plugin install metadata: {exc}") from exc
    if not isinstance(value, dict):
        raise _pc().PluginOperationError("Plugin install metadata must be a JSON object.")
    return value


def _write_install_metadata(metadata: dict[str, dict[str, object]]) -> None:
    """Atomically replace the profile-local plugin install metadata sidecar."""
    path = _install_metadata_path()
    atomic_write_text(
        path, json.dumps(metadata, indent=2, sort_keys=True) + "\n", tmp_prefix=f"{path.name}.tmp-")


_INSTALL_METADATA_LOCK_HOLDER = threading.local()


@contextmanager
def _install_metadata_lock():
    """Serialize read-modify-write of the sidecar across threads and processes. Installs overlap (the
    Desktop install card runs its rows a second apart); each held a snapshot read before its clone, so
    the later write dropped the earlier plugin's record."""
    from hermes_cli.auth import _file_lock

    path = _install_metadata_path()
    with _file_lock(path.with_name(f"{path.name}.lock"), _INSTALL_METADATA_LOCK_HOLDER, 10.0,
                    "Timed out waiting for the plugin install metadata lock"):
        yield


def _update_install_record(name: str, update: Callable[[Optional[dict]], Optional[dict]]) -> None:
    """Rewrite one plugin's record in the CURRENT sidecar, under the lock. *update* maps the current
    record (None when absent) to the new one (None removes it); every other record is re-read here,
    never carried over from a caller's earlier snapshot."""
    with _install_metadata_lock():
        metadata = _pc()._read_install_metadata()
        record = update(metadata.get(name))
        if record is None:
            if name not in metadata:
                return
            del metadata[name]
        else:
            metadata[name] = record
        _pc()._write_install_metadata(metadata)


def pinned_revision(name: str, metadata: Optional[dict] = None) -> Optional[str]:
    """Full SHA a ``--ref`` install of *name* is pinned to, else ``None``."""
    entry = (metadata if metadata is not None else _pc()._read_install_metadata()).get(name)
    if isinstance(entry, dict) and entry.get("pinned") is True and isinstance(entry.get("revision"), str):
        return entry["revision"]
    return None


def _pin_annotation(name: str, metadata: dict) -> Optional[str]:
    sha = pinned_revision(name, metadata)
    return f"git pinned@{sha[:8]}" if sha else None


def _normalize_exact_revision(ref: str) -> str:
    """Lowercase a full 40-hex commit SHA; anything else is a PluginOperationError."""
    if not isinstance(ref, str) or not _EXACT_COMMIT_RE.fullmatch(ref):
        raise _pc().PluginOperationError("--ref must be a full 40-character commit SHA.")
    return ref.lower()


def _safe_git_error(result: subprocess.CompletedProcess, source_url: str = "") -> str:
    """Diagnosable Git output without echoing embedded credentials."""
    from agent.redact import redact_sensitive_text
    error = (result.stderr or result.stdout or "").strip()
    if source_url:
        error = error.replace(source_url, _scrub_git_url(source_url))
    return redact_sensitive_text(error)


def _git_or_raise(
    git_exe: str, repo: Path, *args: str, failure_prefix: str, timeout: int = 60, source_url: str = "",
    auth_url: str = "",
) -> subprocess.CompletedProcess:
    """Run git in *repo*; on a non-zero exit raise PluginOperationError(prefix + scrubbed error)."""
    result = _pc()._run_plugin_git(git_exe, repo, *args, timeout=timeout, auth_url=auth_url)
    if result.returncode != 0:
        raise _pc().PluginOperationError(failure_prefix + _safe_git_error(result, source_url),
                                         failure_class="clone_failed")
    return result


def _git_head_revision(repo: Path, git_exe: str) -> str:
    return _git_or_raise(
        git_exe, repo, "rev-parse", "HEAD", timeout=15,
        failure_prefix="Could not determine installed Git revision:\n",
    ).stdout.strip().lower()


def _git_resolve_commit(repo: Path, git_exe: str, revision: str) -> str:
    """The COMMIT a revision names, peeling annotated tags.

    A catalog pin is 40 hex, but that does not make it a commit: a tag object
    has a sha of its own, and a pin recorded as `git rev-parse <tag>` names the
    tag object, not the commit it points at. Git detaches at the commit, so
    comparing HEAD against the tag object's sha refuses a correct checkout
    (and the catalog installer then cannot install that entry at all). Peeling
    first keeps the guard — HEAD must still BE that commit — while admitting
    the pins authors actually publish. Returns `revision` unchanged when it
    resolves to nothing, so the mismatch guard below still fires.
    """
    try:
        result = _pc()._run_plugin_git(
            git_exe, repo, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}", timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return revision
    resolved = result.stdout.strip().lower()
    return resolved if result.returncode == 0 and resolved else revision


def _checkout_exact_revision(repo: Path, git_exe: str, revision: str, source_url: str = "") -> None:
    """Fetch and detach at one immutable commit, then verify the resulting HEAD. The checkout is
    a network verb too: in a partial (subdirectory) clone it downloads the file contents."""
    timeout = _pc()._clone_timeout_seconds()
    for verb, args, failure_prefix in (
        ("fetch", ("fetch", "--depth", "1", "origin", revision), f"Git commit '{revision}' could not be fetched:\n"),
        ("checkout", ("checkout", "--detach", revision), f"Git checkout of commit '{revision}' failed:\n"),
    ):
        try:
            _git_or_raise(git_exe, repo, *args, failure_prefix=failure_prefix, source_url=source_url,
                          auth_url=source_url, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise _pc().PluginOperationError(
                f"Git {verb} of commit '{revision}' timed out after {timeout} seconds. {_pc()._CLONE_TIMEOUT_HINT}",
                failure_class="clone_failed") from exc
    actual = _pc()._git_head_revision(repo, git_exe)
    if actual != _git_resolve_commit(repo, git_exe, revision):
        raise _pc().PluginOperationError(
            f"Checked-out revision '{actual}' does not match requested commit '{revision}'.",
            failure_class="clone_failed")


def _scrub_git_url(git_url: str) -> str:
    """Strip credentials and query/fragment data from an HTTP Git URL."""
    parsed = urllib.parse.urlsplit(git_url)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return git_url


def _canonical_source(git_url: str, subdir: Optional[str]) -> str:
    scrubbed = _scrub_git_url(git_url)
    return f"{scrubbed}#{subdir}" if subdir else scrubbed


def _scrub_cloned_origin(repo: Path, git_exe: str, git_url: str) -> None:
    """Ensure credentials used for cloning do not survive in ``.git/config``."""
    scrubbed = _scrub_git_url(git_url)
    if scrubbed != git_url:
        _git_or_raise(
            git_exe, repo, "remote", "set-url", "origin", scrubbed, timeout=15,
            failure_prefix="Could not sanitize installed Git remote:\n", source_url=git_url)


def _restrict_checkout_to_subdir(repo: Path, git_exe: str, subdir: str) -> None:
    """Sparse-check-out only *subdir*. Written as the classic ``info/sparse-checkout`` file
    rather than ``git sparse-checkout set`` so older Git clients work too."""
    _git_or_raise(git_exe, repo, "config", "core.sparseCheckout", "true", timeout=15,
                  failure_prefix="Could not enable sparse checkout:\n")
    pattern_file = repo / ".git" / "info" / "sparse-checkout"
    pattern_file.parent.mkdir(parents=True, exist_ok=True)
    escaped = re.sub(r"([\\*?\[])", r"\\\1", subdir.strip("/"))
    pattern_file.write_text(f"/{escaped}/\n", encoding="utf-8")


def _clone_plugin_repo(tmp_clone: Path, git_url: str, revision: Optional[str],
                       subdir: Optional[str] = None) -> str:
    """Shallow-clone *git_url* into *tmp_clone* (detached at *revision* when given), scrub any
    credentials from the recorded origin, and return the installed HEAD SHA.

    A *subdir* install is a blobless clone with a sparse checkout of that subdirectory: a plugin
    living in a monorepo (Hindsight: 170 MB at depth 1, 2 MB for its plugin folder) otherwise
    downloads every file in the repository, which times out on slow connections."""
    git_exe = _pc()._resolve_git_executable()
    if not git_exe:
        raise _pc().PluginOperationError("git is not installed or not in PATH.", failure_class="git_missing")
    clone_timeout = _pc()._clone_timeout_seconds()
    partial = ["--filter=blob:none"] if subdir else []
    no_checkout = ["--no-checkout"] if revision or subdir else []
    clone_args = ["clone", "--depth", "1", *partial, *no_checkout, git_url, str(tmp_clone)]
    try:
        result = _pc()._run_plugin_git(git_exe, tmp_clone.parent, *clone_args, auth_url=git_url,
                                 timeout=clone_timeout)
    except FileNotFoundError as e:
        raise _pc().PluginOperationError("git is not installed or not in PATH.", failure_class="git_missing") from e
    except subprocess.TimeoutExpired as e:
        raise _pc().PluginOperationError(f"Git clone timed out after {clone_timeout} seconds. {_pc()._CLONE_TIMEOUT_HINT}",
                                         failure_class="clone_failed") from e
    if result.returncode != 0:
        raise _pc().PluginOperationError(_pc()._clone_failure_message(git_url, _safe_git_error(result, git_url)),
                                         failure_class="clone_failed")
    _scrub_cloned_origin(tmp_clone, git_exe, git_url)
    if subdir:
        _restrict_checkout_to_subdir(tmp_clone, git_exe, subdir)
    if revision:
        _checkout_exact_revision(tmp_clone, git_exe, revision, source_url=git_url)
    elif subdir:
        try:
            _git_or_raise(git_exe, tmp_clone, "checkout", "HEAD", timeout=clone_timeout, source_url=git_url,
                          auth_url=git_url, failure_prefix="Git checkout of the plugin subdirectory failed:\n")
        except subprocess.TimeoutExpired as e:
            raise _pc().PluginOperationError(
                f"Git checkout timed out after {clone_timeout} seconds. {_pc()._CLONE_TIMEOUT_HINT}",
                failure_class="clone_failed") from e
    return _pc()._git_head_revision(tmp_clone, git_exe)


def _run_plugin_git(
    git_exe: str, target: Path, *args: str, timeout: int = 60, auth_url: str = "",
) -> subprocess.CompletedProcess:
    """Run one git command inside a plugin checkout (non-interactive). *auth_url* names the remote
    a network verb talks to; it runs anonymously first and a stored user credential for that host
    is attached only when the remote refuses anonymous access (private repos)."""
    from hermes_cli.git_credentials import run_git_with_credential_fallback
    return run_git_with_credential_fallback(
        [git_exe, *args], auth_url, env=noninteractive_git_env(), capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=timeout, cwd=str(target))
