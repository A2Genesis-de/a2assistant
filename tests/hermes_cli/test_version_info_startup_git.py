"""A Hermes start from a git checkout must not walk git for the release it never uses.

Each case runs in a fresh interpreter (the suite's conftest pre-seeds the version cache) with a
``git`` shim on PATH that logs every invocation before running the real git.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run_logging_git(tmp_path: Path, code: str) -> tuple[dict, list[str]]:
    real_git = shutil.which("git")
    if real_git is None:
        pytest.skip("git not installed")
    home = tmp_path / "home"
    # Version resolution falls back to <HERMES_HOME>/hermes-agent when the executing tree has no
    # .git (sdist/archive test runs); give it a tagged checkout so the release walk always has one.
    repo = home / "hermes-agent"
    repo.mkdir(parents=True)
    # The fixture's own git ignores the developer's config (signing, hooks): run_tests.sh keeps the
    # real HOME, so a global commit.gpgsign would otherwise prompt for or fail on a key.
    fixture_env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    git = [real_git, "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-C", str(repo)]
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "r"], ["tag", "v1.2.3"]):
        subprocess.run([*git, *args], check=True, env=fixture_env)

    log = tmp_path / "git.log"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "git"
    shim.write_text(f'#!/bin/sh\necho "$*" >> "{log}"\nexec "{real_git}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTHONPATH": str(ROOT),
        "HERMES_HOME": str(home),
    }
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", timeout=120, check=False, stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    calls = log.read_text(encoding="utf-8-sig").splitlines() if log.exists() else []
    return json.loads(out.stdout.strip().splitlines()[-1]), calls


@pytest.mark.platforms("linux", "macos")
def test_startup_checkout_sha_read_is_one_rev_parse(tmp_path):
    code = (
        "import json\n"
        "from hermes_cli.update_cmd_fleet import _current_checkout_sha\n"
        "sha = _current_checkout_sha()\n"
        "print(json.dumps({'sha': sha}))\n"
    )
    result, calls = _run_logging_git(tmp_path, code)

    assert calls == ["rev-parse HEAD"]
    assert result["sha"] and len(result["sha"]) == 40
