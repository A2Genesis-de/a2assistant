"""Tests for ``hermes debug`` CLI command and debug utilities."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    """Set up an isolated HERMES_HOME with minimal logs."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))

    # Create log files
    logs_dir = home / "logs"
    logs_dir.mkdir()
    (logs_dir / "agent.log").write_text(
        "2026-04-12 17:00:00 INFO agent: session started\n"
        "2026-04-12 17:00:01 INFO tools.terminal: running ls\n"
        "2026-04-12 17:00:02 WARNING agent: high token usage\n"
    )
    (logs_dir / "errors.log").write_text(
        "2026-04-12 17:00:05 ERROR gateway.run: connection lost\n"
    )
    (logs_dir / "gateway.log").write_text(
        "2026-04-12 17:00:10 INFO gateway.run: started\n"
    )
    (logs_dir / "gui.log").write_text(
        "2026-04-12 17:00:12 INFO hermes_cli.web_server: dashboard request\n"
    )
    (logs_dir / "desktop.log").write_text(
        "2026-04-12 17:00:15 INFO desktop: backend spawned\n"
    )

    return home


class TestCaptureLogSnapshot:
    """Test _capture_log_snapshot for log reading and truncation."""




    def test_race_truncate_after_resolve_reports_empty(self, hermes_home, monkeypatch):
        """If the log is truncated between resolve and stat, say 'empty', not 'missing'."""
        log_path = hermes_home / "logs" / "agent.log"
        from hermes_cli import debug

        monkeypatch.setattr(debug, "_resolve_log_path", lambda _name: log_path)
        log_path.write_text("")

        snap = debug._capture_log_snapshot("agent", tail_lines=10)
        assert snap.path == log_path
        assert snap.full_text is None
        assert snap.tail_text == "(file empty)"


    def test_keeps_first_line_when_truncation_on_boundary(self, hermes_home):
        """When truncation lands on a line boundary, keep the first full line."""
        from hermes_cli.debug import _capture_log_snapshot

        # File must exceed the initial chunk_size (8192) used by the
        # backward-reading loop so the truncation path actually fires.
        line = "A" * 99 + "\n"  # 100 bytes per line
        num_lines = 200  # 20000 bytes
        (hermes_home / "logs" / "agent.log").write_bytes((line * num_lines).encode("utf-8"))

        # max_bytes = 1000 = 100 * 10 → cut at byte 20000 - 1000 = 19000,
        # and byte 19000 - 1 is '\n'.  Boundary hit → keep all 10 lines.
        snap = _capture_log_snapshot("agent", tail_lines=5, max_bytes=1000)
        assert snap.full_text is not None
        assert "truncated" in snap.full_text
        raw = snap.full_text.split("\n", 1)[1]
        kept = [l for l in raw.strip().splitlines() if l.startswith("A")]
        assert len(kept) == 10


class TestMissingLogNote:
    """A missing log explains itself when the writer isn't this backend.

    `hermes debug share` runs on the backend, so a desktop connected to a
    remote/docker/SSH backend can never contribute desktop.log. Reporting a
    bare absence sends triage after a client-side bug it cannot see.
    """

    def test_backend_written_log_reports_plain_absence(self, hermes_home):
        from hermes_cli.debug import _capture_log_snapshot

        (hermes_home / "logs" / "agent.log").unlink()

        snap = _capture_log_snapshot("agent", tail_lines=10)
        assert snap.full_text is None
        assert snap.tail_text == "(file not found)"

    def test_client_written_log_names_its_writer_and_path(self, hermes_home):
        from hermes_cli.debug import _capture_log_snapshot

        (hermes_home / "logs" / "desktop.log").unlink()

        snap = _capture_log_snapshot("desktop", tail_lines=10)
        assert snap.full_text is None
        assert "not on this host" in snap.tail_text
        # The reader needs the path to collect by hand on the client machine.
        assert str(hermes_home / "logs" / "desktop.log") in snap.tail_text

    def test_present_client_log_is_captured_normally(self, hermes_home):
        """A local backend still reads desktop.log — the note is only for a miss."""
        from hermes_cli.debug import _capture_log_snapshot

        snap = _capture_log_snapshot("desktop", tail_lines=10)
        assert "backend spawned" in snap.tail_text
        assert "not on this host" not in snap.tail_text

    def test_empty_client_log_is_empty_not_absent(self, hermes_home):
        """An empty file means the app ran and logged nothing — a different fact."""
        from hermes_cli.debug import _capture_log_snapshot

        (hermes_home / "logs" / "desktop.log").write_text("")

        snap = _capture_log_snapshot("desktop", tail_lines=10)
        assert snap.tail_text == "(file empty)"

    def test_report_carries_the_note_for_a_remote_backend(self, hermes_home):
        """The uploaded report — what people paste into support — must explain it."""
        from hermes_cli.debug import collect_debug_report

        (hermes_home / "logs" / "desktop.log").unlink()

        report = collect_debug_report(log_lines=10, dump_text="dump\n")
        assert "--- desktop.log" in report
        assert "not on this host" in report




# ---------------------------------------------------------------------------
# Capture log redaction (force=True applies regardless of HERMES_REDACT_SECRETS)
# ---------------------------------------------------------------------------

# A vendor-prefixed token used across redaction tests. Long enough to clear
# the redactor's `floor` parameter so it actually masks rather than fully blanks.
_REDACT_FIXTURE_TOKEN = "sk-proj-A1B2C3D4E5F6G7H8I9J0aA"


class TestCaptureLogSnapshotRedaction:
    """Pin upload-time redaction at the _capture_log_snapshot boundary."""

    @pytest.fixture
    def hermes_home_with_secret(self, tmp_path, monkeypatch):
        """Isolated HERMES_HOME whose agent.log contains a vendor-prefixed token."""
        home = tmp_path / ".hermes"
        home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(home))
        # Baseline fixture: no explicit env-var opinion. With the post-#17691
        # default of ON, the default-path tests below exercise the
        # secure-default behaviour. The `force=True` regression test
        # setenvs to "false" inline to prove force=True works even when
        # the runtime flag is disabled.
        monkeypatch.delenv("HERMES_REDACT_SECRETS", raising=False)

        logs_dir = home / "logs"
        logs_dir.mkdir()
        (logs_dir / "agent.log").write_text(
            f"2026-04-12 17:00:00 INFO config: api_key={_REDACT_FIXTURE_TOKEN} loaded\n"
        )
        (logs_dir / "errors.log").write_text("")
        (logs_dir / "gateway.log").write_text("")
        return home

    def test_default_redacts_tail_and_full_text(self, hermes_home_with_secret):
        from hermes_cli.debug import _capture_log_snapshot

        snap = _capture_log_snapshot("agent", tail_lines=10)

        # Both views the upload uses must be sanitized.
        assert _REDACT_FIXTURE_TOKEN not in snap.tail_text
        assert snap.full_text is not None
        assert _REDACT_FIXTURE_TOKEN not in snap.full_text

    def test_redact_false_passes_through(self, hermes_home_with_secret):
        from hermes_cli.debug import _capture_log_snapshot

        snap = _capture_log_snapshot("agent", tail_lines=10, redact=False)

        # Original token survives when the caller opts out.
        assert _REDACT_FIXTURE_TOKEN in snap.tail_text
        assert _REDACT_FIXTURE_TOKEN in (snap.full_text or "")

    def test_force_true_works_when_redaction_disabled(
        self, hermes_home_with_secret, monkeypatch
    ):
        """Regression test: redact_sensitive_text short-circuits without force=True.

        If a future refactor drops `force=True` from `redact_debug_support_text`, this
        test fails immediately. Without `force=True`, the redactor returns the
        input unchanged when HERMES_REDACT_SECRETS=false, and the share-time
        redaction feature ships silently broken for users who opted out of
        runtime redaction (e.g. developers working on the redactor itself).
        """

        # Force the runtime flag off so we're exercising the force=True path,
        # not the default-on path.
        monkeypatch.setenv("HERMES_REDACT_SECRETS", "false")

        from hermes_cli.debug import _capture_log_snapshot

        assert os.environ.get("HERMES_REDACT_SECRETS", "") == "false"

        snap = _capture_log_snapshot("agent", tail_lines=10)

        assert _REDACT_FIXTURE_TOKEN not in snap.tail_text
        assert snap.full_text is not None
        assert _REDACT_FIXTURE_TOKEN not in snap.full_text

    def test_default_redacts_email_addresses_for_public_share(
        self, hermes_home_with_secret
    ):
        from hermes_cli.debug import _capture_log_snapshot

        log_path = hermes_home_with_secret / "logs" / "agent.log"
        log_path.write_text(
            "2026-04-12 17:00:00 INFO gateway.run: "
            "inbound message: platform=bluebubbles "
            "user=person@example.com chat=iMessage;-;person@example.com msg='hello'\n"
        )

        snap = _capture_log_snapshot("agent", tail_lines=10)

        assert "person@example.com" not in snap.tail_text
        assert "[REDACTED_EMAIL]" in snap.tail_text
        assert snap.full_text is not None
        assert "person@example.com" not in snap.full_text


    def test_capture_default_log_snapshots_threads_redact(
        self, hermes_home_with_secret
    ):
        from hermes_cli.debug import _capture_default_log_snapshots

        snaps = _capture_default_log_snapshots(50)

        # Default threads redact=True to all three captured logs.
        assert _REDACT_FIXTURE_TOKEN not in snaps["agent"].tail_text
        assert _REDACT_FIXTURE_TOKEN not in (snaps["agent"].full_text or "")

    def test_redacts_complete_log_lines_before_applying_byte_limits(
        self, hermes_home_with_secret
    ):
        from hermes_cli.debug import _capture_log_snapshot

        max_bytes = 512
        raw_window = 8192
        tail_canary = "r36_REDACTED_tail_boundary_canary_012345"
        full_canary = "r36_REDACTED_full_boundary_canary_678901"
        payload = bytearray(b"x" * 12_000)

        # The backwards-read window and the final full-log window each begin
        # inside a credential field. Truncating first drops ``accessToken=``
        # while retaining its complete value, which the redactor cannot then
        # classify. A redacted share must either scrub the complete logical
        # line before either cap or omit that partial line.
        for boundary, canary in (
            (len(payload) - raw_window, tail_canary),
            (len(payload) - max_bytes, full_canary),
        ):
            marker = f"accessToken={canary}".encode()
            start = boundary - len("accessToken=")
            payload[start:start + len(marker)] = marker

        (hermes_home_with_secret / "logs" / "agent.log").write_bytes(payload)

        snap = _capture_log_snapshot("agent", tail_lines=1, max_bytes=max_bytes)

        assert tail_canary not in snap.tail_text
        assert snap.full_text is not None
        assert full_canary not in snap.full_text



# ---------------------------------------------------------------------------
# Debug report collection
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# CLI entry point — run_debug_share
# ---------------------------------------------------------------------------

class TestRunDebugShare:
    """``hermes debug share`` prints the report and full logs locally."""

    def test_share_prints_report_and_full_logs(self, hermes_home, capsys):
        from types import SimpleNamespace

        from hermes_cli.debug import run_debug_share

        with patch("hermes_cli.dump.run_dump") as mock_dump:
            mock_dump.side_effect = lambda a: print("--- hermes dump ---\nversion: test\n--- end dump ---")
            run_debug_share(SimpleNamespace(lines=50))

        out = capsys.readouterr().out
        for name in ("agent.log", "gateway.log", "gui.log", "desktop.log"):
            assert f"FULL {name}" in out
            assert f"--- full {name} ---" in out
        assert "--- hermes dump ---" in out

    def test_share_never_prompts(self, hermes_home, capsys, monkeypatch):
        from types import SimpleNamespace

        from hermes_cli.debug import run_debug_share

        def _boom(_):
            raise AssertionError("input() must not be called")

        monkeypatch.setattr("builtins.input", _boom)
        with patch("hermes_cli.dump.run_dump"):
            run_debug_share(SimpleNamespace(lines=50))
        assert "FULL agent.log" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Share-time redaction wiring + visible banner
# ---------------------------------------------------------------------------

class TestRunDebugShareRedaction:
    """End-to-end: --no-redact flag, banner injection, default behavior."""

    @pytest.fixture
    def hermes_home_with_secret(self, tmp_path, monkeypatch):
        """Isolated HERMES_HOME whose agent.log contains a vendor-prefixed token."""
        home = tmp_path / ".hermes"
        home.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(home))
        monkeypatch.delenv("HERMES_REDACT_SECRETS", raising=False)

        logs_dir = home / "logs"
        logs_dir.mkdir()
        (logs_dir / "agent.log").write_text(
            f"2026-04-12 17:00:00 INFO config: api_key={_REDACT_FIXTURE_TOKEN} loaded\n"
        )
        (logs_dir / "errors.log").write_text("")
        (logs_dir / "gateway.log").write_text(
            f"2026-04-12 17:00:01 INFO gateway.run: token {_REDACT_FIXTURE_TOKEN}\n"
        )
        return home

    def test_default_share_redacts_printed_content(
        self, hermes_home_with_secret, capsys
    ):
        """The printed report and full logs do not contain the raw token."""
        from hermes_cli.debug import run_debug_share

        args = MagicMock()
        args.lines = 50
        args.no_redact = False

        with patch("hermes_cli.dump.run_dump"):
            run_debug_share(args)

        out = capsys.readouterr().out
        assert "FULL agent.log" in out
        assert _REDACT_FIXTURE_TOKEN not in out

    def test_fallback_provider_key_never_reaches_upload_bound_content(self, hermes_home_with_secret):
        """``hermes dump`` quotes ``fallback_providers`` from config.yaml; neither the CLI share
        bundle nor the gateway /debug report may carry a fallback entry's api_key."""
        from hermes_cli.debug import _capture_dump, collect_debug_report, collect_share_bundle

        fallback_key = "fbk-opaque-0123456789abcdefghij"
        (hermes_home_with_secret / "config.yaml").write_text(
            "fallback_providers:\n"
            "  - provider: custom\n"
            "    model: backup-model\n"
            "    base_url: https://backup.example/v1\n"
            f"    api_key: {fallback_key}\n", encoding="utf-8")

        uploads = [*collect_share_bundle(log_lines=20).values(),
                   collect_debug_report(log_lines=20, dump_text=_capture_dump())]

        assert any("backup-model" in text for text in uploads)  # the dump really ran
        assert not [text for text in uploads if fallback_key in text]

    @pytest.mark.parametrize(("yaml_value", "secret"), [
        ("87419362508741936250", "87419362508741936250"),  # unquoted: YAML int
        ("'opaque***Fallback0123456789'", "opaque***Fallback0123456789"),  # looks pre-masked
        ("{value: nestedOpaque0123456789abcdef}", "nestedOpaque0123456789abcdef"),
    ])
    def test_fallback_api_key_masked_whatever_its_yaml_shape(self, hermes_home_with_secret, yaml_value, secret):
        """The runtime ``str()``s any ``api_key`` value (fallback_config.resolve_entry_api_key), so the
        dump masks the field itself rather than relying on text redaction to recognise the value."""
        from hermes_cli.debug import _capture_dump, collect_debug_report, collect_share_bundle

        (hermes_home_with_secret / "config.yaml").write_text(
            "fallback_providers:\n"
            "  - provider: custom\n"
            "    model: backup-model\n"
            f"    api_key: {yaml_value}\n", encoding="utf-8")

        texts = [_capture_dump(redact=False),  # `hermes dump` stdout, as printed
                 *collect_share_bundle(log_lines=20).values(),
                 collect_debug_report(log_lines=20, dump_text=_capture_dump())]

        assert "backup-model" in texts[0]
        assert not [text for text in texts if secret in text]

    @pytest.mark.parametrize(("field", "yaml_value", "secret"), [
        ("token", "87419362508741936250", "87419362508741936250"),
        ("auth_token", "'opaque***AuthToken0123456789'", "opaque***AuthToken0123456789"),
        ("client_secret", "{value: clientSecretOpaque0123456789}", "clientSecretOpaque0123456789"),
        ("password", "98127364509812736450", "98127364509812736450"),
        ("clientApiKey", "'opaque***CamelKey0123456789'", "opaque***CamelKey0123456789"),
    ])
    def test_fallback_secret_fields_masked_by_repo_policy(self, hermes_home_with_secret, field, yaml_value, secret, capsys):
        """Every field ``agent.redact`` treats as a credential is masked by field, not only ``api_key``;
        env-var names and token budgets stay readable."""
        from hermes_cli.debug import _capture_dump, collect_debug_report, run_debug_share

        (hermes_home_with_secret / "config.yaml").write_text(
            "fallback_providers:\n"
            "  - provider: custom\n"
            "    model: backup-model\n"
            "    key_env: BACKUP_KEY_ENV_NAME\n"
            "    api_key_env: BACKUP_API_KEY_ENV_NAME\n"
            "    max_tokens: 4321\n"
            f"    {field}: {yaml_value}\n", encoding="utf-8")

        run_debug_share(MagicMock(lines=20, no_redact=False))
        printed = capsys.readouterr().out

        assert "backup-model" in printed
        assert secret not in printed

        texts = [_capture_dump(redact=False),  # `hermes dump` stdout, as printed
                 collect_debug_report(log_lines=20, dump_text=_capture_dump())]

        assert all(s in texts[0] for s in ("backup-model", "BACKUP_KEY_ENV_NAME", "BACKUP_API_KEY_ENV_NAME", "4321"))
        assert not [text for text in texts if secret in text]

    @pytest.mark.parametrize("base_url", [
        "https://user:{s}@backup.example/v1",
        "https://backup.example/v1?key={s}",
        "https://backup.example/v1?X-Amz-Signature={s}",
        "https://backup.example/v1?X-Goog-Signature={s}",
        "https://backup.example/v1?sv=2024-11-04&sig={s}",
        "https://backup.example/v1#access_token={s}&view=public",
    ])
    def test_fallback_base_url_credential_never_reaches_upload_bound_content(self, hermes_home_with_secret, base_url):
        """A fallback ``base_url`` can carry its credential in the URL (userinfo, query, fragment). The
        dump is config made to be pasted, so ``hermes dump`` itself and every upload of it get strict
        URL-credential redaction, not the log policy."""
        from hermes_cli.debug import _capture_dump, collect_debug_report, collect_share_bundle

        secret = "urlCredOpaque0123456789abcdef"
        (hermes_home_with_secret / "config.yaml").write_text(
            "fallback_providers:\n"
            "  - provider: custom\n"
            "    model: backup-model\n"
            f"    base_url: '{base_url.format(s=secret)}'\n", encoding="utf-8")

        texts = [_capture_dump(redact=False),  # `hermes dump` stdout, as printed
                 *collect_share_bundle(log_lines=20).values(),
                 collect_debug_report(log_lines=20, dump_text=_capture_dump())]

        assert all("backup-model" in text and "backup.example" in text for text in texts[:2])
        assert not [text for text in texts if secret in text]

    def test_capture_dump_is_independent_strict_redaction_boundary(self):
        """A future dump formatting mistake cannot leak through debug upload paths."""
        from hermes_cli.debug import _capture_dump

        raw_key = "opaqueBoundaryKeyABC123456789"
        raw_password = "boundaryPasswordABC123456789"
        raw_signature = "boundarySignatureABC123456789"

        def leaky_dump(_args):
            print(
                "{'api_key': '" + raw_key + "', "
                "'base_url': 'https://user:" + raw_password
                + "@example.test/v1?X-Amz-Signature=" + raw_signature + "'}"
            )

        with patch("hermes_cli.dump.run_dump", side_effect=leaky_dump):
            safe = _capture_dump()
            raw = _capture_dump(redact=False)

        for secret in (raw_key, raw_password, raw_signature):
            assert secret not in safe
            assert secret in raw

    def test_default_share_includes_redaction_banner(
        self, hermes_home_with_secret, capsys
    ):
        from hermes_cli.debug import run_debug_share

        args = MagicMock()
        args.lines = 50
        args.no_redact = False

        with patch("hermes_cli.dump.run_dump"):
            run_debug_share(args)

        assert "log content redacted" in capsys.readouterr().out

    def test_no_redact_flag_disables_redaction_and_banner(
        self, hermes_home_with_secret, capsys
    ):
        from hermes_cli.debug import run_debug_share

        args = MagicMock()
        args.lines = 50
        args.no_redact = True

        with patch("hermes_cli.dump.run_dump"):
            run_debug_share(args)

        out = capsys.readouterr().out
        assert _REDACT_FIXTURE_TOKEN in out
        assert "log content redacted" not in out


# ---------------------------------------------------------------------------
# run_debug router
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Argparse integration
# ---------------------------------------------------------------------------

class TestCollectShareBundle:


    def test_redaction_keeps_secrets_out(self, hermes_home):
        from hermes_cli.debug import collect_share_bundle

        secret = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
        (hermes_home / "logs" / "agent.log").write_text(
            f"line one\nOPENAI_API_KEY={secret}\nline three\n"
        )
        with patch("hermes_cli.dump.run_dump"):
            redacted = collect_share_bundle(log_lines=50, redact=True)
            unredacted = collect_share_bundle(log_lines=50, redact=False)

        # Sanity: without redaction the secret is present in the bundle.
        assert secret in "\n".join(unredacted.values())
        # With redaction it must be scrubbed everywhere.
        assert secret not in "\n".join(redacted.values())

    def test_redaction_masks_url_credentials(self, hermes_home):
        """Log-time redaction leaves ``?token=`` and ``user:pass@`` in URLs for tool flows;
        the upload must not carry them."""
        from hermes_cli.debug import collect_share_bundle

        query_token = "Q7fK2mZp9RtX4vLb8NcW1yHs"
        password = "Pw7Kq2Lm9Xs4Vb"
        (hermes_home / "logs" / "agent.log").write_text(
            "2026-09-29 01:00:00 INFO plugins.web.firecrawl.provider: Firecrawl scraping: "
            f"https://files.example.com/export.csv?token={query_token}&page=2\n"
            f"2026-09-29 01:00:01 INFO agent: using proxy http://alice:{password}@10.0.0.5:3128\n"
        )
        with patch("hermes_cli.dump.run_dump"):
            bundle = "\n".join(collect_share_bundle(log_lines=50, redact=True).values())

        assert query_token not in bundle
        assert password not in bundle
        # Query credentials are masked in place; strict URL redaction masks the
        # complete userinfo field while preserving the host and port.
        assert "export.csv?token=***&page=2" in bundle
        assert "***:***@10.0.0.5:3128" in bundle




class TestDebugSlashCommand:
    """`/debug` in the CLI/TUI handler.

    The classic CLI and the TUI slash worker both dispatch through
    ``HermesCLI.process_command`` → ``_handle_debug_command(cmd_original)``,
    which prints the local report through ``run_debug_share``.
    """

    def _handler(self):
        from hermes_cli.cli_commands_mixin import CLICommandsMixin

        class _Stub(CLICommandsMixin):
            pass

        return _Stub()._handle_debug_command

    def _captured(self, cmd_original):
        captured = {}

        def _fake_run(args):
            captured.update(vars(args))

        with patch("hermes_cli.debug.run_debug_share", _fake_run):
            self._handler()(cmd_original)
        return captured

    def test_debug_prints_locally(self):
        assert self._captured("/debug") == {"lines": 200}
