"""Which tool calls the a2-elevation policy treats as protected, and with which scope."""

import pytest

from tests.plugins.a2_elevation.conftest import load

policy = load("policy")


@pytest.mark.parametrize(("tool", "args", "scope", "label"), [
    ("terminal", {"command": "cat ~/Admin/keys/asc.env"}, "protected", "Schlüsselordner ~/Admin/keys"),
    ("terminal", {"command": "ls /Users/j.drude/Admin/keys/"}, "protected", "Schlüsselordner ~/Admin/keys"),
    ("read_file", {"path": "~/Admin/keys/AuthKey.p8"}, "protected", "Schlüsselordner ~/Admin/keys"),
    ("search_files", {"paths": ["/tmp", "/Users/j.drude/Admin/keys"]}, "protected", "Schlüsselordner ~/Admin/keys"),
    ("write_file", {"file_path": "~/Library/Keychains/login.keychain-db"}, "protected", "Schlüsselbund"),
    ("terminal", {"command": "security find-generic-password -s foo -w"}, "protected", "Schlüsselbund"),
    ("terminal", {"command": "security dump-keychain"}, "protected", "Schlüsselbund"),
    ("terminal", {"command": "security unlock-keychain login.keychain"}, "protected", "Schlüsselbund"),
    ("terminal", {"command": "ssh a2-server uptime"}, "protected", "Produktionsserver"),
    ("terminal", {"command": "ssh -o ConnectTimeout=5 kraftmatch-server 'docker ps'"}, "protected", "Produktionsserver"),
    ("terminal", {"command": "scp dump.sql babau-server:/tmp/"}, "protected", "Produktionsserver"),
    ("terminal", {"command": "rsync -a site/ gunna-server:/var/www/"}, "protected", "Produktionsserver"),
    ("execute_code", {"code": "subprocess.run(['ssh', 'a2-server', 'ls'])"}, "protected", "Produktionsserver"),
    ("terminal", {"command": "ping a2-denise.a2.internal"}, "protected", "Gerät a2-denise"),
    ("terminal", {"command": "sudo launchctl list"}, "admin", "Administratorrechte (sudo)"),
    ("terminal", {"command": "cd /tmp && sudo rm -f x"}, "admin", "Administratorrechte (sudo)"),
    ("terminal", {"command": "true; sudo -v"}, "admin", "Administratorrechte (sudo)"),
])
def test_protected_calls_need_the_matching_scope(tool, args, scope, label):
    rule = policy.required_scope(tool, args)

    assert rule is not None
    assert (rule.scope, rule.label) == (scope, label)


@pytest.mark.parametrize(("tool", "args"), [
    ("terminal", {"command": "ls ~/Dev && git status"}),
    ("terminal", {"command": "ssh a2-workstation uptime"}),
    ("terminal", {"command": "ssh a2-macbook ls"}),
    ("terminal", {"command": "echo a2-server is down"}),
    ("terminal", {"command": "security list-keychains"}),
    ("terminal", {"command": "pseudo-tool --flag"}),
    ("terminal", {"command": "visudo-check"}),
    ("read_file", {"path": "~/Dev/a2genesis/hermes-agent/README.md"}),
    ("read_file", {"path": "~/Admin/network/hosts"}),
    ("web_search", {"query": "~/Admin/keys sudo a2-denise"}),
    ("terminal", "sudo not-a-dict"),
    ("terminal", None),
])
def test_unprotected_calls_pass(tool, args):
    assert policy.required_scope(tool, args) is None
