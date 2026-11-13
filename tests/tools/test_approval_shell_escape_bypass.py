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
