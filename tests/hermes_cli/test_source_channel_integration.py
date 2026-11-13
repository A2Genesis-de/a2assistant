"""Source channel tracers through real Git and completion boundaries."""
import argparse
from copy import deepcopy
import subprocess
from types import SimpleNamespace

import pytest

from hermes_cli import main, source_releases, update_cmd
from hermes_cli.config import require_readable_config_before_write
from hermes_cli.subcommands.update import build_update_parser
from hermes_cli.update_channel import (
    _write_channel_record, channel_record, install_id, set_install_channel)

# These tests model the stable lookup themselves.
pytestmark = pytest.mark.real_release_channels


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout.strip()


@pytest.fixture
def source(tmp_path, monkeypatch):
    home, origin, checkout = (tmp_path / name for name in ("home", "origin", "checkout"))
    home.mkdir()
    origin.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_INSTALL_ROOT", str(checkout))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    git(origin, "init", "-b", "main")
    git(origin, "config", "user.name", "Channel Fixture")
    git(origin, "config", "user.email", "fixture@example.invalid")
    git(origin, "config", "commit.gpgsign", "false")
    commits = []
    for label in ("installed", "published", "unpublished"):
        (origin / "content.txt").write_text(label)
        git(origin, "add", "content.txt")
        git(origin, "commit", "-m", label)
        commits.append(git(origin, "rev-parse", "HEAD"))
    git(tmp_path, "clone", str(origin), str(checkout))
    git(checkout, "checkout", "--detach", commits[0])
    monkeypatch.setattr(main, "PROJECT_ROOT", checkout)
    monkeypatch.setattr("hermes_cli.config.get_project_root", lambda: checkout)
    parser = argparse.ArgumentParser()
    build_update_parser(parser.add_subparsers(), cmd_update=main.cmd_update)
    opts = update_cmd._UpdateOptions(pre_update_version=None, gw_input_fn=None,
        assume_yes=True, keep_stash=False, switch_branch=False, discard_local_changes=False)
    monkeypatch.setattr(update_cmd, "_resolve_update_options", lambda *_: opts)
    monkeypatch.setattr(update_cmd, "_begin_update_receipt_and_plan", lambda *_: None)
    monkeypatch.setattr(main, "_run_pre_update_backup", lambda *_: None)
    monkeypatch.setattr(main, "_pause_windows_gateways_for_update", lambda: None)
    monkeypatch.setattr(update_cmd, "_prepare_git_command", lambda **_: (False, ["git"]))
    return SimpleNamespace(home=home, origin=origin, root=checkout, commits=commits, parser=parser)


def publish_stable(monkeypatch, source):
    monkeypatch.setattr(source_releases, "_resolve_stable", lambda repository, *_: source_releases.SourceTarget(
        "stable", repository, commit=source.commits[1], version="1.2.3"))


def saved(source):
    return channel_record(require_readable_config_before_write(source.home / "config.yaml"), source.root)


def test_unknown_source_channel_is_refused_when_set(source):
    with pytest.raises(ValueError, match="main or stable"):
        set_install_channel("canary", source.root)
    assert saved(source) == {}


@pytest.mark.parametrize("channel", ["preview-not-registered", "canary", "stable"])
def test_unavailable_channel_cannot_fall_back_to_main(source, monkeypatch, channel):
    from hermes_cli import source_check

    _write_channel_record(install_id(source.root), str(source.root), channel)

    def unpublished(*_args):
        raise ValueError("No published stable release")

    monkeypatch.setattr(source_releases, "_resolve_stable", unpublished)
    status = source_check.check_for_updates(install_root=source.root, home=source.home, force=True)
    assert status["error"] == "release-unavailable"
    assert "targetSha" not in status
    before = git(source.root, "rev-parse", "HEAD")
    with pytest.raises(SystemExit):
        update_cmd._cmd_update_impl(source.parser.parse_args(["update", "--yes"]), False)
    assert git(source.root, "rev-parse", "HEAD") == before


def test_main_follows_the_git_branch(source):
    from hermes_cli import source_check

    set_install_channel("main", source.root)
    target = source_releases.resolve_source_target("main", ["git"], source.root)
    assert target.branch == "main" and target.commit is None
    status = source_check.check_for_updates(install_root=source.root, home=source.home, force=True)
    assert "error" not in status, status
    assert status["targetSha"] == source.commits[2]


def test_stable_check_apply_is_pinned_not_branch_tip(source, monkeypatch, capsys):
    set_install_channel("stable", source.root)
    publish_stable(monkeypatch, source)
    update_cmd._cmd_update_check()
    assert "stable" in capsys.readouterr().out
    assert git(source.root, "rev-parse", "HEAD") == source.commits[0]
    completed = []
    monkeypatch.setattr(update_cmd, "_complete_source_update", lambda request: completed.append(deepcopy(request)))
    update_cmd._cmd_update_impl(source.parser.parse_args(["update", "--yes"]), False)
    assert git(source.root, "rev-parse", "HEAD") == source.commits[1]
    assert (source.root / "content.txt").read_text() == "published"
    assert completed[0]["expected_sha"] == source.commits[1]
    assert saved(source)["channel"] == "stable"


def test_explicit_branch_needs_no_release_lookup(source, monkeypatch):
    def forbidden(*_args):
        pytest.fail("explicit source branch resolved a release")

    monkeypatch.setattr(source_releases, "_resolve_stable", forbidden)
    set_install_channel("stable", source.root)
    completed = []
    monkeypatch.setattr(update_cmd, "_complete_source_update", lambda request: completed.append(request))
    update_cmd._cmd_update_impl(source.parser.parse_args(["update", "--branch", "main"]), False)
    assert git(source.root, "rev-parse", "HEAD") == source.commits[2]
    assert saved(source)["channel"] == "stable"


@pytest.mark.parametrize("dirty", [False, True])
def test_pinned_zip_apply_uses_the_release_source_archive(source, monkeypatch, dirty):
    import urllib.request

    set_install_channel("stable", source.root)
    publish_stable(monkeypatch, source)
    archive = source.home / "source.zip"
    git(source.origin, "archive", "--format=zip", "--prefix=hermes-agent-fixture/",
        "--output=" + str(archive), source.commits[1])
    urls = []

    def download(url, filename):
        import shutil
        urls.append(url)
        shutil.copyfile(archive, filename)

    monkeypatch.setattr(urllib.request, "urlretrieve", download)
    monkeypatch.setattr(update_cmd, "_prepare_git_command", lambda **_: (True, ["git"]))
    completed = []
    monkeypatch.setattr(update_cmd, "_complete_source_update", lambda req: completed.append(deepcopy(req)))
    if dirty:
        (source.root / "notes.txt").write_text("do not remove")
        with pytest.raises(SystemExit):
            update_cmd._cmd_update_impl(source.parser.parse_args(["update"]), False)
        assert not urls and not completed
        assert (source.root / "content.txt").read_text() == "installed"
        assert (source.root / "notes.txt").read_text() == "do not remove"
    else:
        update_cmd._cmd_update_impl(source.parser.parse_args(["update"]), False)
        assert urls == [f"https://github.com/A2Genesis-de/a2assistant/archive/{source.commits[1]}.zip"]
        assert (source.root / "content.txt").read_text() == "published"
        assert completed[0]["expected_sha"] == source.commits[1]


def test_changed_checkout_cannot_repin_selected_channel_during_apply(source, monkeypatch):
    set_install_channel("stable", source.root)
    publish_stable(monkeypatch, source)
    pull = update_cmd._pull_updates

    def moved(*args, **kwargs):
        before = pull(*args, **kwargs)
        git(source.root, "checkout", "--detach", source.commits[2])
        return before

    monkeypatch.setattr(update_cmd, "_pull_updates", moved)
    completed = []
    monkeypatch.setattr(update_cmd, "_complete_source_update", lambda req: completed.append(req))
    with pytest.raises(SystemExit):
        update_cmd._cmd_update_impl(source.parser.parse_args(["update"]), False)
    assert not completed
    assert saved(source)["channel"] == "stable"
