"""Voice-mode / auto-TTS methods for GatewayRunner (split out of ``gateway/run.py``; bound via
the MRO). ``gateway.run`` internals are imported lazily inside method bodies (import cycle), so
``patch("gateway.run.X")`` keeps intercepting them at call time."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from typing import Optional

from gateway.config import Platform
from gateway.platforms.base import build_auto_tts_output_path
from gateway.platforms.event import MessageEvent, MessageType
from gateway.session import SessionSource

logger = logging.getLogger("gateway.run")  # log-record parity with the origin module

# Adapter-side per-chat auto-TTS override sets (``/voice off`` vs explicit ``/voice on``/``tts``).
_OFF_SET, _ON_SET = "_auto_tts_disabled_chats", "_auto_tts_enabled_chats"
_VOICE_MODES = {"off", "voice_only", "all"}


class GatewayVoiceMixin:
    def _voice_key(self, platform: Platform, chat_id: str, profile: Optional[str] = None) -> str:
        """``<profile>:<platform>:<chat_id>`` under multiplexing (else two bots in one channel
        share a key and one ``/voice`` flips the other's); default keeps ``<platform>:<chat>``.

        Under multiplexing the key is additionally namespaced by the profile whose bot speaks in the chat
        (``<profile>:<platform>:<chat_id>``); the default profile keeps the historical
        ``<platform>:<chat_id>`` shape so persisted state stays valid. See #75198.
        """
        base = f"{platform.value}:{chat_id}"
        profile = profile.strip() if isinstance(profile, str) else ""
        return base if not profile or profile == "default" else f"{profile}:{base}"

    def _voice_key_for_source(self, source: SessionSource) -> str:
        """Voice mode belongs to the (bot, chat) pair: namespace is the profile that OWNS the
        receiving adapter, not the routed profile."""
        profile = self._adapter_profile_for_source(source)
        return self._voice_key(source.platform, source.chat_id, profile=profile)

    def _load_voice_modes(self) -> dict[str, str]:
        try:
            data = json.loads(self._VOICE_MODE_PATH.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        items = {str(k): m for k, m in data.items() if m in _VOICE_MODES}
        for key in (k for k in items if ":" not in k):  # legacy unprefixed key: warn and skip
            logger.warning(
                "Skipping legacy unprefixed voice mode key %r during migration. "
                "Re-enable voice mode on that chat to rebuild the prefixed key.", key)
        return {k: m for k, m in items.items() if ":" in k}

    def _save_voice_modes(self) -> None:
        try:
            self._VOICE_MODE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._voice_mode, indent=2)
            self._VOICE_MODE_PATH.write_text(payload, encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to save voice modes: %s", e)

    @staticmethod
    def _toggle_adapter_auto_tts_set(adapter, chat_id: str, on: bool, *, enable: bool) -> None:
        """Add/discard ``chat_id`` in the adapter's enabled (``enable=True``) or disabled set;
        adding also clears the other set (``/voice off`` and ``/voice on``/``tts`` override)."""
        add_to, clear_from = (_ON_SET, _OFF_SET) if enable else (_OFF_SET, _ON_SET)
        if not isinstance(target := getattr(adapter, add_to, None), set):
            return
        if not on:
            target.discard(chat_id)
            return
        target.add(chat_id)
        if isinstance(other := getattr(adapter, clear_from, None), set):
            other.discard(chat_id)

    def _set_adapter_auto_tts_disabled(self, adapter, chat_id: str, disabled: bool) -> None:
        self._toggle_adapter_auto_tts_set(adapter, chat_id, disabled, enable=False)

    def _set_adapter_auto_tts_enabled(self, adapter, chat_id: str, enabled: bool) -> None:
        self._toggle_adapter_auto_tts_set(adapter, chat_id, enabled, enable=True)

    def _apply_voice_mode(self, adapter, voice_key: str, chat_id: str, mode: str) -> None:
        """Record+persist ``mode``; mirror into adapter sets (``off`` -> disabled, else enabled)."""
        self._voice_mode[voice_key] = mode
        self._save_voice_modes()
        self._toggle_adapter_auto_tts_set(adapter, chat_id, True, enable=mode != "off")

    def _sync_voice_mode_state_to_adapter(self, adapter) -> None:
        """Restore persisted /voice state into a live adapter: ``_auto_tts_default`` from
        ``voice.auto_tts``; enabled (voice_only/all) / disabled (off) sets from ``_voice_mode``."""
        platform = getattr(adapter, "platform", None)
        if not isinstance(platform, Platform):
            return
        chat_sets = [
            (chats, modes)
            for name, modes in ((_OFF_SET, {"off"}), (_ON_SET, {"voice_only", "all"}))
            if isinstance(chats := getattr(adapter, name, None), set)
        ]
        if not chat_sets:
            return
        try:
            from hermes_cli.config import load_config  # lazy: no gateway -> hermes_cli module dep
            auto_tts_default = bool((load_config().get("voice") or {}).get("auto_tts", False))
        except Exception:
            auto_tts_default = False
        if hasattr(adapter, "_auto_tts_default"):
            adapter._auto_tts_default = auto_tts_default
        prefix = self._voice_key(platform, "", profile=getattr(adapter, "_owner_profile", None))
        for chats, modes in chat_sets:
            chats.clear()
            chats.update(key[len(prefix):] for key, mode in self._voice_mode.items()
                         if mode in modes and key.startswith(prefix))

    def _should_send_voice_reply(
        self, event: MessageEvent, response: str, agent_messages: list, already_sent: bool = False
    ) -> bool:
        """False when voice_mode is off for this chat, the response is empty/an error, the agent
        already called text_to_speech this turn, or voice input + base adapter auto-TTS handled it
        — UNLESS streaming consumed the response (already_sent): then the runner must do it."""
        if not response or response.startswith("Error:"):
            return False
        # A local session's speech plays in its own client: LocalSessionAdapter has no audio delivery,
        # so an owner-side synthesis would be a paid provider call nobody hears.
        if event.source.platform == Platform.LOCAL:
            return False
        chat_id = event.source.chat_id
        voice_mode = self._voice_mode.get(self._voice_key_for_source(event.source))
        is_voice_input = event.message_type == MessageType.VOICE
        adapter = self._delivery_adapter_for(event.source)
        adapter_auto_tts = False
        with suppress(Exception):  # adapters without the probe read as False
            adapter_auto_tts = bool(adapter._should_auto_tts_for_chat(chat_id))
        # ``voice.auto_tts`` (synced into the adapter at startup) is the fallback only when the
        # chat has no explicit mode; the chat-level all/voice_only/off choice takes precedence.
        if not (voice_mode == "all" or (voice_mode == "voice_only" and is_voice_input)
                or (voice_mode is None and adapter_auto_tts)):
            logger.debug(
                "Auto voice reply skipped: mode=%s adapter_auto_tts=%s chat=%s platform=%s",
                voice_mode, adapter_auto_tts, chat_id, event.source.platform.value)
            return False
        # Dedup: agent already called the TTS tool in THIS turn (from the last user message on).
        start = next((i for i, m in reversed(list(enumerate(agent_messages)))
                      if m.get("role") == "user"), 0)
        if any((tc.get("function") or {}).get("name") == "text_to_speech"
               for msg in agent_messages[start:] if msg.get("role") == "assistant"
               for tc in (msg.get("tool_calls") or [])):
            return False
        # Dedup: base adapter auto-TTS already handles voice input (play_tts plays in VC when
        # supported) — unless streaming consumed the text (already_sent): then the runner must.
        return not (is_voice_input and not already_sent)

    def _should_echo_stt_transcripts(self) -> bool:
        return bool(getattr(self.config, "stt_echo_transcripts", True))

    async def _send_voice_reply(self, event: MessageEvent, text: str) -> None:
        """Generate TTS audio and send as a voice message before the text reply. The TTS tool
        may return one combined file or several separately valid ones (combination unavailable /
        over a platform limit); legacy single-file results keep working."""
        audio_path, actual_paths = None, []
        try:
            from tools.tts_text_normalize import _strip_markdown_for_tts
            from tools.tts_tool import text_to_speech_tool
            tts_text = _strip_markdown_for_tts(text)
            if not tts_text:
                return
            # Platforms whose native voice bubbles require Ogg/Opus (OPUS_VOICE_PLATFORMS) get an
            # explicit .ogg path; the TTS tool's container repair guarantees real Ogg/Opus bytes.
            audio_path = build_auto_tts_output_path(event.source.platform)
            raw = await asyncio.to_thread(text_to_speech_tool, text=tts_text,
                                          output_path=audio_path)
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Auto voice reply TTS returned invalid JSON: %s",
                               raw[:200] if raw else raw)
                return
            candidates = result.get("file_paths") or [result.get("file_path", audio_path)]
            paths = [str(p) for p in candidates if p and os.path.isfile(p)]
            if not result.get("success") or not paths:
                logger.warning("Auto voice reply TTS failed: %s", result.get("error"))
                return
            actual_paths = paths
            await self._deliver_voice_reply(event, actual_paths)
        except Exception as e:
            logger.warning("Auto voice reply failed: %s", e, exc_info=True)
        finally:
            for p in ({audio_path, *actual_paths} - {None}):
                with suppress(OSError):
                    os.unlink(p)

    async def _deliver_voice_reply(self, event: MessageEvent, audio_paths: list[str]) -> None:
        """Send the files as voice messages."""
        adapter = self._delivery_adapter_for(event.source)
        if not callable(send_voice := getattr(adapter, "send_voice", None)):
            return
        reply_anchor = self._reply_anchor_for_event(event)
        # notify=True mirrors the final-text path in platforms/base.py so notification-gating
        # adapters (Telegram "important" mode) deliver it. Clone: shared w/ typing-indicator state.
        thread_meta = dict(self._thread_metadata_for_source(event.source, reply_anchor) or {})
        thread_meta["notify"] = True
        for path in audio_paths:
            await send_voice(chat_id=event.source.chat_id, audio_path=path, reply_to=reply_anchor,
                             metadata=thread_meta)
