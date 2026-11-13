"""N86: every legacy-fallback verb from a ticket bound to a secondary profile runs in THAT profile,
and a ticket whose profile home vanished is refused instead of falling back to the launch profile.
"""
import threading
import types

import pytest


@pytest.fixture
def homes(tmp_path, monkeypatch):
    from tui_gateway import server
    launch = tmp_path / 'root'
    bee = launch / 'profiles' / 'bee'
    bee.mkdir(parents=True)
    monkeypatch.setenv('HERMES_HOME', str(launch))
    monkeypatch.setattr(server, '_hermes_home', launch)
    return server, launch, bee


def _call(server, profile_id, method, params):
    from gateway.runtime_bootstrap import _PURPOSE_CAPABILITIES
    from tui_gateway.ws_legacy_fallback import dispatch_legacy
    actor = types.SimpleNamespace(profile_id=str(profile_id), capabilities=frozenset(_PURPOSE_CAPABILITIES['interactive']))
    written, done = [], threading.Event()
    transport = types.SimpleNamespace(write=lambda frame: written.append(frame) or done.set() or True)
    reply = dispatch_legacy(server, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}, transport, actor)
    return reply if reply is not None else (done.wait(10) and written[0])


def test_ticket_whose_home_vanished_is_refused_not_the_launch_profile(homes):
    server, _launch, bee = homes
    gone = bee.parent / 'gone'
    reply = _call(server, gone, 'shared_metrics.status', {})
    assert reply['error']['code'] == 4064, reply
