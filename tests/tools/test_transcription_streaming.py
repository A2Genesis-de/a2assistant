"""Live STT sessions: wire behaviour over a real socket, and the recorder hand-off."""

from __future__ import annotations

import json
import threading

from websockets.sync.server import serve

from tools import transcription_streaming as ts
from tools import voice_mode


def _openai_like_server(received: list):
    """OpenAI Realtime transcription shape: a delta per audio append, the final on commit."""

    def handler(ws):
        words = []
        for raw in ws:
            event = json.loads(raw)
            if event.get("type") == "input_audio_buffer.append":
                received.append(event["audio"])
                word = f"w{len(words)}"
                words.append(word)
                ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.delta",
                                    "delta": word if len(words) == 1 else f" {word}"}))
            elif event.get("type") == "input_audio_buffer.commit":
                ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed",
                                    "transcript": " ".join(words)}))
                return

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_live_session_streams_partials_before_end():
    received: list = []
    server = _openai_like_server(received)
    port = server.socket.getsockname()[1]
    partials: list = []
    seen_partial = threading.Event()

    def on_partial(text):
        partials.append(text)
        seen_partial.set()

    session = ts.OpenAIRealtimeSession("k", f"http://127.0.0.1:{port}/v1", "gpt-live-transcribe", "en",
                                       None, on_partial).start()
    session.push_audio(b"\x01\x00" * 160)
    session.push_audio(b"\x02\x00" * 160)
    assert seen_partial.wait(5), "a partial must arrive while audio is still streaming"
    result = session.finalize(timeout=5)
    server.shutdown()

    assert result == {"success": True, "transcript": "w0 w1", "provider": "openai"}
    assert len(received) == 2
    assert partials[-1] == "w0 w1"


class _Session:
    def __init__(self, result):
        self.result, self.ended = result, False

    def end_audio(self):
        self.ended = True

    def finalize(self):
        return self.result

    def cancel(self):
        pass


def test_recording_uses_the_live_transcript_and_falls_back_to_the_file(tmp_path, monkeypatch):
    uploads: list = []
    monkeypatch.setattr("tools.transcription_tools.transcribe_audio",
                        lambda path, **kw: uploads.append(path) or {"success": True, "transcript": "from file"})
    live_wav, failed_wav = str(tmp_path / "a.wav"), str(tmp_path / "b.wav")

    live = _Session({"success": True, "transcript": "from live", "provider": "openai"})
    voice_mode._park_live_session(live_wav, live)
    assert live.ended, "parking ends the audio so the provider flushes while the caller works"
    assert voice_mode.transcribe_recording(live_wav)["transcript"] == "from live"
    assert uploads == []

    voice_mode._park_live_session(failed_wav, _Session({"success": False, "transcript": "", "error": "socket"}))
    assert voice_mode.transcribe_recording(failed_wav)["transcript"] == "from file"
    assert uploads == [failed_wav]
