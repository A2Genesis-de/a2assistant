"""Native admission keeps main's inbound contract: real adapter events run a turn (N78-N80)."""
import ast
from dataclasses import replace
from pathlib import Path

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.event import MessageEvent
from gateway.run import GatewayRunner
from gateway.session_authority import initialize_session_authority
from gateway.session_envelope import restore_native, snapshot_native
from hermes_state_runtime import RuntimeStoreError

REPO = Path(__file__).resolve().parents[2]
CHAT = '15551234567'


@pytest.mark.asyncio
async def test_native_codec_closed_metadata_contract_and_reply_expected(tmp_path, monkeypatch):
    from plugins.platforms.telegram.adapter import TelegramAdapter
    monkeypatch.setenv('TELEGRAM_ALLOWED_USERS', '15551234567')
    runner = GatewayRunner(GatewayConfig(sessions_dir=tmp_path / 'sessions'))
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:abc"))
    runner.adapters = {Platform.TELEGRAM: adapter}
    authority = await initialize_session_authority(runner, profile_id='default', instance_id='codec')
    try:
        event = MessageEvent(text='chatter', source=adapter.build_source(chat_id=CHAT, user_id=CHAT, chat_type='group'),
                             message_id='c1')
        # Slack-style silence policy survives the envelope (N80); unknown stays absent (old digest).
        assert 'reply_expected' not in snapshot_native(runner, event)['native_text_v1']['event']
        for value in (False, True):
            assert restore_native(snapshot_native(runner, replace(event, reply_expected=value))).reply_expected is value
        refused = [{'internal': True}, {'gateway_session_id': 's'},
                   {'_authorization_profile_home': '/x'}, {'arbitrary': 1}]
        for metadata in refused:
            with pytest.raises(RuntimeStoreError, match='invalid_params'):
                snapshot_native(runner, replace(event, metadata=metadata))
        for bad in (replace(event, reply_expected='no'), replace(event, text='/new now')):
            with pytest.raises(RuntimeStoreError, match='invalid_params'):
                snapshot_native(runner, bad)
        # MSG-2: an adapter's absent media list (None) is no media at the envelope boundary, with the
        # same fingerprint as []; any other non-list still refuses.
        for name in ('media_urls', 'media_types', 'media_text_inlined'):
            assert snapshot_native(runner, replace(event, **{name: None})) == snapshot_native(runner, event)
            for bad in ('x', ('x',)):
                with pytest.raises(RuntimeStoreError, match='invalid_params'):
                    snapshot_native(runner, replace(event, **{name: bad}))
    finally:
        authority.db.close()
    # No adapter stamps MessageEvent.metadata on ordinary inbound. A new producer must extend the contract.
    producers = set()
    for path in [*REPO.glob('gateway/platforms/**/*.py'), *REPO.glob('plugins/platforms/**/*.py')]:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Call) and getattr(node.func, 'id', getattr(node.func, 'attr', '')) == 'MessageEvent'
                    and any(k.arg == 'metadata' for k in node.keywords)):
                producers.add(path.relative_to(REPO).as_posix())
    assert producers == set(), producers
