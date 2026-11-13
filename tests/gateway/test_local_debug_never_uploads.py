"""``/debug`` never uploads: a local session gets the redacted report, a chat gets a pointer."""
import socket
from unittest.mock import patch

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _runner():
    from gateway.run import GatewayRunner
    runner = object.__new__(GatewayRunner)
    runner._running_agents = {}

    async def _inline(fn, *args):
        return fn(*args)

    runner._run_in_executor_with_context = _inline
    return runner


def _event(platform, text):
    source = SessionSource(platform=platform, chat_id='chat-1', user_id='u1', chat_type='dm')
    return MessageEvent(text=text, source=source)


class _NoNetwork:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError('network call during /debug')


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['/debug', '/debug local'])
async def test_local_session_debug_returns_the_report(text):
    guard = _NoNetwork()
    bundle = {'report': 'REDACTED-REPORT-BODY', 'agent.log': 'FULL-LOG'}
    with patch('hermes_cli.debug.collect_share_bundle', return_value=bundle), \
            patch.object(socket.socket, 'connect', guard):
        out = await _runner()._handle_debug_command(_event(Platform.LOCAL, text))
    assert guard.calls == []
    assert 'REDACTED-REPORT-BODY' in out


@pytest.mark.asyncio
async def test_messaging_debug_is_refused_without_collecting():
    guard = _NoNetwork()
    with patch('hermes_cli.debug.collect_share_bundle', guard), \
            patch.object(socket.socket, 'connect', guard):
        out = await _runner()._handle_debug_command(_event(Platform.TELEGRAM, '/debug'))
    assert guard.calls == []
    assert 'hermes debug share' in out


@pytest.mark.asyncio
async def test_local_debug_real_collector_opens_no_socket(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    guard = _NoNetwork()
    with patch.object(socket.socket, 'connect', guard), \
            patch.object(socket.socket, 'connect_ex', guard), \
            patch('socket.create_connection', guard):
        out = await _runner()._handle_debug_command(_event(Platform.LOCAL, '/debug'))
    assert guard.calls == []
    assert 'hermes dump' in out
