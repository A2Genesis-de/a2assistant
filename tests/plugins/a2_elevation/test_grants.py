"""GrantStore: time-limited grants, scope coverage, revoke and the audit trail."""

import json
import stat

import pytest

from tests.plugins.a2_elevation.conftest import load

grants = load("grants")


def _audit(store_dir):
    return [json.loads(line) for line in (store_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()]


def test_grant_is_current_and_private(store, tmp_path):
    grant = store.grant("protected", "Deploy prüfen", channel="mac")

    assert store.current() == grant
    assert grant.expires_at - grant.granted_at == grants.GRANT_SECONDS
    assert stat.S_IMODE((tmp_path / "elevation" / "grant.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "elevation").stat().st_mode) == 0o700


@pytest.mark.parametrize(("granted", "wanted", "covered"), [
    ("protected", "protected", True),
    ("protected", "admin", False),
    ("admin", "admin", True),
    ("admin", "protected", True),
])
def test_scope_coverage(store, granted, wanted, covered):
    grant = store.grant(granted, "x", channel="mac")

    assert grant.covers(wanted, store.now()) is covered


def test_grant_expires_after_ten_minutes(store, clock, tmp_path):
    store.grant("admin", "Update", channel="mac")

    clock.advance(grants.GRANT_SECONDS - 1)
    assert store.current().seconds_left(store.now()) == 1

    clock.advance(1)
    assert store.current() is None
    assert not (tmp_path / "elevation" / "grant.json").exists()


def test_revoke_ends_the_grant_and_is_audited(store, tmp_path):
    store.grant("protected", "Schlüssel lesen", channel="telegram", actor="Joel")

    revoked = store.revoke()

    assert revoked.scope == "protected"
    assert store.current() is None
    assert store.revoke() is None
    events = _audit(tmp_path / "elevation")
    assert [entry["event"] for entry in events] == ["granted", "revoked"]


def test_audit_records_channel_and_actor(store, tmp_path):
    store.grant("protected", "Schlüssel lesen", channel="telegram", actor="Joel")
    store.audit("denied", "admin", "sudo", channel="mac")

    granted, denied = _audit(tmp_path / "elevation")
    assert granted | {"at": None} == {"at": None, "event": "granted", "scope": "protected",
                                      "reason": "Schlüssel lesen", "channel": "telegram", "actor": "Joel"}
    assert denied["channel"] == "mac"
    assert "actor" not in denied
    assert stat.S_IMODE((tmp_path / "elevation" / "audit.jsonl").stat().st_mode) == 0o600


def test_corrupt_grant_file_means_no_grant(store, tmp_path):
    (tmp_path / "elevation").mkdir()
    (tmp_path / "elevation" / "grant.json").write_text("{not json", encoding="utf-8")

    assert store.current() is None


def test_grant_written_before_channels_existed_still_loads(store, clock, tmp_path):
    (tmp_path / "elevation").mkdir()
    legacy = {"scope": "protected", "reason": "alt", "granted_at": clock.now, "expires_at": clock.now + 60}
    (tmp_path / "elevation" / "grant.json").write_text(json.dumps(legacy), encoding="utf-8")

    assert store.current().channel == ""
