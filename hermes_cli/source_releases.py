"""Resolve the source update target: the main branch, or a published stable release."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import subprocess
import urllib.error

from hermes_cli.repository import REPOSITORY
from hermes_cli.update_channel import SOURCE_CHANNELS, STABLE_TAG_RE

logger = logging.getLogger(__name__)
_GITHUB_ORIGIN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", re.IGNORECASE,
)
_SHA = re.compile(r"[0-9a-f]{40}")


def source_repository(git_cmd=None, cwd=None) -> str:
    """The GitHub repository of ``origin``; other origins resolve to the A2Assistant repository."""
    if git_cmd is not None:
        from hermes_cli.source_check import source_git_env

        result = subprocess.run(
            [*git_cmd, "config", "--get", "remote.origin.url"], cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            stdin=subprocess.DEVNULL, env=source_git_env(),
            check=False,
        )
        match = _GITHUB_ORIGIN.fullmatch(result.stdout.strip())
        if result.returncode == 0 and match:
            return match[1]
    return REPOSITORY


@dataclass(frozen=True)
class SourceTarget:
    """A pinned stable release or the main branch."""

    channel: str
    repository: str
    commit: str | None = None
    branch: str | None = None
    version: str | None = None
    ahead: bool = False

    @property
    def label(self) -> str:
        if self.ahead:
            return (f"{self.channel} v{self.version}; this checkout is newer and waits for the next release"
                    " (`hermes update --set-channel main` follows every commit)")
        return f"{self.channel} v{self.version} ({self.commit[:12]})" if self.commit else self.channel


def resolve_source_target(channel: str, git_cmd=None, cwd=None, *, repository=None,
                          forward_only: bool = False) -> SourceTarget:
    """Resolve a subscription: stable from GitHub releases, main from the git branch.

    ``forward_only`` (an unchosen default subscription) pins a checkout that already
    contains the release to its own HEAD, so the update is a no-op instead of a downgrade.
    """
    target = _resolve_source_target(channel, git_cmd, cwd, repository=repository)
    if forward_only and target.commit and git_cmd is not None and cwd is not None:
        head = _head_containing(git_cmd, cwd, target.commit, target.repository)
        if head is not None and head != target.commit:
            from dataclasses import replace

            return replace(target, commit=head, ahead=True)
    return target


def _probe(git_cmd, cwd, *args):
    """``git <args>`` in ``cwd``, or None when git did not answer: an unknown relation, not a claim.

    Before the updater's fetch the release commit is usually absent, and git 2.43 spends 7-12 s
    of CPU on a blobless clone failing to find it even with lazy fetch off (#137646).
    """
    from hermes_cli.source_check import source_git_env

    try:
        return subprocess.run(
            [*git_cmd, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, stdin=subprocess.DEVNULL, env=source_git_env(),
            check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git %s did not answer: %s", " ".join(args), exc)
        return None


def _head_containing(git_cmd, cwd, commit: str, repository: str) -> str | None:
    """HEAD's sha unless HEAD is PROVEN not to contain ``commit``, then None.

    An unchosen default must never move a checkout backward on a guess, so an
    unknown relation (shallow history, GitHub unreachable) keeps HEAD.
    """
    from hermes_cli.source_check import _github_compare, source_git_env

    head = subprocess.run(
        [*git_cmd, "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=10, stdin=subprocess.DEVNULL, env=source_git_env(), check=False,
    ).stdout.strip()
    if not _SHA.fullmatch(head):
        return None
    # An unanswered probe falls through to the comparison API, as a shallow checkout's does.
    ancestry = _probe(git_cmd, cwd, "merge-base", "--is-ancestor", commit, head)
    if ancestry is not None and ancestry.returncode == 0:
        return head
    # A shallow boundary makes exit 1 a guess; full history makes it proof.
    if ancestry is not None and ancestry.returncode == 1:
        shallow = _probe(git_cmd, cwd, "rev-parse", "--is-shallow-repository")
        if shallow is not None and shallow.stdout.strip() == "false":
            return None
    status = (_github_compare(commit, head, repository) or {}).get("status")
    return None if status in ("behind", "diverged") else head


def _resolve_source_target(channel: str, git_cmd=None, cwd=None, *, repository=None) -> SourceTarget:
    if channel not in SOURCE_CHANNELS:
        raise ValueError(f"Unknown update channel {channel!r}; source installs follow main or stable")
    repository = repository or source_repository(git_cmd, cwd)
    if channel == "stable":
        return _resolve_stable(repository, git_cmd, cwd)
    return SourceTarget(channel, repository, branch="main")


def _describe_release_failure(failure: BaseException) -> str:
    """A transport failure names its cause (a rate limit is not "no release")."""
    if isinstance(failure, (urllib.error.URLError, TimeoutError)):
        from hermes_cli.github_api import describe_github_failure

        # The request that failed, not the configuration: a rejected token retries anonymously.
        return describe_github_failure(failure, authenticated=getattr(failure, "hermes_authenticated", False))
    return f"No published stable release could be verified: {failure}"


def _resolve_stable(repository: str, git_cmd=None, cwd=None) -> SourceTarget:
    """Stable IS the repository's latest published GitHub release: the tag a release
    publishes (non-draft, non-prerelease, strict vX.Y.Z), verified against origin.
    Publishing the release is the only promotion.
    """
    try:
        tag, commit = _resolve_release(git_cmd, cwd, repository=repository)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning("Could not resolve the stable source release: %s", exc)
        raise ValueError(_describe_release_failure(exc)) from exc
    return SourceTarget("stable", repository, commit=commit, version=str(tag).removeprefix("v"))


def _published(release) -> bool:
    return (isinstance(release, dict) and release.get("draft") is False and release.get("prerelease") is False
            and isinstance(release.get("tag_name"), str) and bool(STABLE_TAG_RE.fullmatch(release["tag_name"])))


def _json(url: str):
    """GitHub API JSON with the updater's credential ladder (token, gh, anonymous).

    Anonymous api.github.com is 60 requests/hour per address, so an unauthenticated
    stable lookup fails for everyone behind one office, CI or container exit.
    """
    from hermes_cli.source_check import _request

    return json.loads(_request(url))


def _resolve_release(git_cmd=None, cwd=None, *, repository=None) -> tuple[str, str]:
    """``resolve_source_release`` that raises the failure instead of returning ``(None, None)``."""
    repository = repository or source_repository(git_cmd, cwd)
    base = f"https://api.github.com/repos/{repository}"
    release = _json(f"{base}/releases/latest")
    if not _published(release):
        raise ValueError("No published stable release")
    tag = release["tag_name"]
    commit = _json(f"{base}/commits/{tag}")
    sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError(f"No published commit for release {tag}")
    if git_cmd is not None:
        from hermes_cli.source_check import source_git_env

        ref = f"refs/tags/{tag}"
        result = subprocess.run(
            [*git_cmd, "ls-remote", "--tags", "origin", ref, ref + "^{}"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True, timeout=60, stdin=subprocess.DEVNULL,
            env=source_git_env(),
        )
        refs = dict((parts[1], parts[0]) for line in result.stdout.splitlines()
                    if len(parts := line.split()) == 2)
        if refs.get(ref + "^{}", refs.get(ref)) != sha:
            raise ValueError(f"Origin tag {tag} does not match the published release commit")
    return tag, sha


def resolve_source_release(channel: str, git_cmd=None, cwd=None, *, repository=None,
                           pointer: bool = True) -> tuple[str | None, str | None]:
    """The latest published stable release ``(tag, commit)``, or ``(None, None)``.

    Kept for updaters that load it from the new tree after the checkout swap; only
    ``stable`` exists and ``pointer`` is accepted for their call shape.
    """
    del pointer
    if channel != "stable":
        return None, None
    try:
        return _resolve_release(git_cmd, cwd, repository=repository)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning("Could not resolve the stable source release: %s", exc)
        return None, None
