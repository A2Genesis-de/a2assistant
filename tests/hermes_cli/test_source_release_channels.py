"""Release-channel checks and updates against actual repositories and HTTP feeds."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace
import subprocess
import urllib.request
from urllib.parse import urlsplit

import pytest

from hermes_cli import main, update_cmd
from hermes_cli.source_releases import resolve_source_release
from hermes_cli.update_channel import set_install_channel

# The fixture serves release metadata over loopback; stable's real GitHub path is the subject.
pytestmark = pytest.mark.real_release_channels


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture(params=["utf-8", "utf-8-sig"])
def releases(tmp_path, monkeypatch, request):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-b", "main")
    git(origin, "config", "user.name", "Release Fixture")
    git(origin, "config", "user.email", "fixture@example.invalid")
    git(origin, "config", "commit.gpgsign", "false")
    git(origin, "config", "tag.gpgsign", "false")
    commits = []
    for label in ("old", "stable", "canary", "unpublished"):
        (origin / "content.txt").write_text(label, encoding="utf-8")
        git(origin, "add", ".")
        git(origin, "commit", "-m", label)
        commits.append(git(origin, "rev-parse", "HEAD"))
    tags = {"stable": "v1.2.3"}
    git(origin, "tag", "-a", tags["stable"], commits[1], "-m", "stable")
    git(origin, "tag", "v99.0.0", commits[3])
    git(origin, "tag", "v99.0.1+canary.20260912T125822Z", commits[3])
    checkout = tmp_path / "checkout"
    git(tmp_path, "clone", str(origin), str(checkout))
    git(checkout, "config", "user.name", "Release Fixture")
    git(checkout, "config", "user.email", "fixture@example.invalid")
    git(checkout, "config", "commit.gpgsign", "false")
    git(checkout, "checkout", "--detach", commits[0])
    monkeypatch.setattr(main, "PROJECT_ROOT", checkout)
    monkeypatch.setenv("HERMES_INSTALL_ROOT", str(checkout))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)

    responses = {}
    requests = []
    responses[f"/repos/A2Genesis-de/a2assistant/commits/{tags['stable']}"] = {"sha": commits[1]}
    responses["/repos/A2Genesis-de/a2assistant/releases/latest"] = {
        "tag_name": tags["stable"], "draft": False, "prerelease": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            data = responses.get(self.path)
            self.send_response(404 if data is None else 200)
            self.end_headers()
            if data is not None:
                self.wfile.write((data if isinstance(data, str) else json.dumps(data)).encode(request.param))

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    open_url = urllib.request.urlopen

    def local_urlopen(request, *args, **kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else request
        parsed = urlsplit(url)
        return open_url(f"http://127.0.0.1:{server.server_port}{parsed.path}"
                        + (f"?{parsed.query}" if parsed.query else ""), *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", local_urlopen)
    yield SimpleNamespace(root=checkout, origin=origin, commits=commits,
                          tags=tags, responses=responses, requests=requests)
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("git_cmd", [["git"], None], ids=["git", "no-git"])
def test_stable_resolution_uses_latest_published_release_not_highest_tag(releases, git_cmd):
    assert resolve_source_release("stable", git_cmd, releases.root) == (
        releases.tags["stable"], releases.commits[1],
    )
    assert releases.requests


@pytest.mark.parametrize("start", ["old", "ahead", "local"])
def test_source_check_and_apply_land_on_selected_release(releases, monkeypatch, capsys, start):
    channel = "stable"
    if start != "old":
        git(releases.root, "checkout", "-b", "my-work", releases.commits[3])
    if start == "local":
        (releases.root / "my-work.txt").write_text("committed local work\n", encoding="utf-8")
        git(releases.root, "add", ".")
        git(releases.root, "commit", "-m", "local work")
        (releases.root / "notes.txt").write_text("uncommitted notes\n", encoding="utf-8")
    branch_sha = git(releases.root, "rev-parse", "HEAD")
    set_install_channel(channel, releases.root)
    before = git(releases.root, "rev-parse", "HEAD")
    update_cmd._cmd_update_check()
    assert releases.tags[channel] in capsys.readouterr().out
    assert git(releases.root, "rev-parse", "HEAD") == before

    # Exercise the real selection/fetch/checkout path, not dependency installation
    # or live service management. No host OS is simulated.
    opts = update_cmd._UpdateOptions(
        pre_update_version=None, gw_input_fn=None,
        assume_yes=True, keep_stash=False, switch_branch=False, discard_local_changes=False,
    )
    monkeypatch.setattr(update_cmd, "_resolve_update_options", lambda *_: opts)
    monkeypatch.setattr(update_cmd, "_begin_update_receipt_and_plan", lambda *_: None)
    monkeypatch.setattr(main, "_run_pre_update_backup", lambda *_: None)
    monkeypatch.setattr(main, "_pause_windows_gateways_for_update", lambda: None)
    monkeypatch.setattr(update_cmd, "_prepare_git_command", lambda **_: (False, ["git"]))
    applied = []
    monkeypatch.setattr(update_cmd, "_complete_source_update", lambda request: applied.append(request))
    args = SimpleNamespace(branch=None, channel=None, force_venv=True)
    update_cmd._cmd_update_impl(args, False)
    expected = releases.commits[1]
    assert len(applied) == 1
    assert applied[0]["expected_sha"] == expected
    assert applied[0]["source"] == str(releases.root.resolve())
    assert git(releases.root, "rev-parse", "HEAD") == expected
    if start != "old":
        assert git(releases.root, "rev-parse", "my-work") == branch_sha
    if start == "local":
        assert (releases.root / "notes.txt").read_text(encoding="utf-8") == "uncommitted notes\n"
    update_cmd._cmd_update_check()
    assert "Up to date with" in capsys.readouterr().out


def test_source_check_honors_transient_channel_without_rewriting_record(releases, capsys):
    set_install_channel("stable", releases.root)
    args = SimpleNamespace(branch=None, channel="main", check=True)
    main.cmd_update(args)
    out = capsys.readouterr().out
    assert "origin/main" in out and releases.tags["stable"] not in out
    update_cmd._cmd_update_check()
    assert releases.tags["stable"] in capsys.readouterr().out


def test_fork_origin_uses_its_own_published_release(releases):
    url = "https://github.com/Fixture/hermes-agent.git"
    git(releases.root, "config", "remote.origin.url", url)
    git(releases.root, "config", f"url.{releases.origin}.insteadOf", url)
    tag = releases.tags["stable"]
    git(releases.origin, "tag", "-f", tag, releases.commits[3])
    releases.responses["/repos/Fixture/hermes-agent/releases/latest"] = {
        "tag_name": tag, "draft": False, "prerelease": False,
    }
    releases.responses[f"/repos/Fixture/hermes-agent/commits/{tag}"] = {"sha": releases.commits[3]}
    assert resolve_source_release("stable", ["git"], releases.root) == (tag, releases.commits[3])
    assert not any(path.startswith("/releases/") for path in releases.requests)


def test_zip_fallback_keeps_selected_repository_and_commit(releases, monkeypatch):
    from hermes_cli import update_cmd_zip

    seen = []
    monkeypatch.setattr(update_cmd_zip, "_abort_zip_update_if_dirty_tree", lambda: None)
    class DownloadBoundary(Exception):
        pass
    def download(branch, url, target_sha=None):
        seen.append((url, target_sha))
        raise DownloadBoundary
    monkeypatch.setattr(update_cmd_zip, "_download_and_swap_zip", download)
    with pytest.raises(DownloadBoundary):
        update_cmd_zip._update_via_zip(
            SimpleNamespace(branch=None), target_sha=releases.commits[2],
            target_repository="Fixture/hermes-agent", completion_request={})
    assert seen == [(f"https://github.com/Fixture/hermes-agent/archive/{releases.commits[2]}.zip",
                     releases.commits[2])]


@pytest.mark.parametrize("git_cmd", [["git"], None], ids=["git", "no-git"])
def test_selected_draft_never_falls_back_to_other_tags(releases, git_cmd):
    releases.responses["/repos/A2Genesis-de/a2assistant/releases/latest"]["draft"] = True
    assert resolve_source_release("stable", git_cmd, releases.root) == (None, None)
    assert not any("/tags?" in path for path in releases.requests)


def test_main_check_still_uses_branch_without_release_requests(releases, capsys):
    set_install_channel("main", releases.root)
    update_cmd._cmd_update_check()
    assert "behind origin/main" in capsys.readouterr().out
    assert releases.requests == []


def test_origin_tag_cannot_substitute_a_fork_commit(releases):
    git(releases.origin, "tag", "-f", releases.tags["stable"], releases.commits[3])
    assert resolve_source_release("stable", ["git"], releases.root) == (None, None)
    # Without git, the same selection remains pinned to the published commit.
    assert resolve_source_release("stable") == (releases.tags["stable"], releases.commits[1])


def test_unconfigured_checkout_of_the_own_repository_follows_main(releases):
    from hermes_cli.update_channel import default_channel

    own = "https://github.com/A2Genesis-de/a2assistant.git"
    git(releases.root, "remote", "set-url", "origin", own)
    assert default_channel(releases.root) == "main"
