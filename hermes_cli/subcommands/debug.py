"""``hermes debug`` subcommand parser."""

from __future__ import annotations

import argparse
from typing import Callable


def build_debug_parser(subparsers, *, cmd_debug: Callable) -> None:
    """Attach the ``debug`` subcommand to ``subparsers``."""
    debug_parser = subparsers.add_parser(
        "debug", help="Debug tools — print logs and system info for support",
        description="Debug utilities for A2Assistant. Use 'hermes debug share' to "
        "print a redacted debug report (system info + recent logs) to copy into a "
        "support request. Nothing is uploaded.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    hermes debug share              Print the redacted debug report
    hermes debug share --lines 500  Include more log lines
    hermes debug share --no-redact  Disable secret redaction
""")
    debug_sub = debug_parser.add_subparsers(dest="debug_command")
    share_parser = debug_sub.add_parser(
        "share", help="Print a redacted debug report (system info + logs)")
    share_parser.add_argument(
        "--lines", type=int, default=200,
        help="Number of log lines to include per log file (default: 200)")
    share_parser.add_argument(
        "--no-redact", action="store_true",
        help="Disable secret redaction (default: redact). Logs are normally run "
            "through agent.redact.redact_sensitive_text with force=True.")
    debug_parser.set_defaults(func=cmd_debug)
