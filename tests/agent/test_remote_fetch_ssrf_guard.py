"""Every remote-party-supplied URL fetch refuses internal targets before a socket opens.

Provider response URLs, model-supplied image refs and manifest-derived pet URLs all route
through ``tools.url_safety``: the URL is checked up
front and every redirect hop is re-validated at TCP connect. A loopback listener records
hits — the invariant is that it sees none for the hostile target.
"""
from __future__ import annotations

import http.server
import importlib
import threading
from pathlib import Path

import pytest

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc00000000201010018dd8db00000000049454e44ae426082"
)
METADATA = "http://169.254.169.254/latest/meta-data/"


class _Handler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.hits.append(self.path)
        if self.path.startswith("/to-metadata"):
            self.send_response(302)
            self.send_header("Location", METADATA)
            self.end_headers()
            return
        if self.path.endswith(".json"):
            body, ctype = b'{"pets": []}', "application/json"
        else:
            body, ctype = PNG, "image/png"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def listener(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    (tmp_path / ".hermes").mkdir()
    _Handler.hits = []
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", _Handler.hits
    httpd.shutdown()



def _fetch_manifest(url: str, monkeypatch):
    from agent.pet import manifest

    monkeypatch.setattr(manifest, "MANIFEST_URL", url)
    return manifest.fetch_manifest(timeout=5, force=True)


SITES = {
    "provider_media.save_url(image)": lambda u, mp, tmp: importlib.import_module(
        "agent.image_gen_provider").save_url_image(u, timeout=5),
    "provider_media.save_url(video)": lambda u, mp, tmp: importlib.import_module(
        "agent.video_gen_provider").save_url_video(u, timeout=5),
    "image_gen/openai::_load_image_bytes": lambda u, mp, tmp: importlib.import_module(
        "plugins.image_gen.openai")._load_image_bytes(u),
    "image_gen/openai-codex::_remote_image_to_data_url": lambda u, mp, tmp: importlib.import_module(
        "plugins.image_gen.openai-codex")._remote_image_to_data_url(u),
    "pet/store::_http_get": lambda u, mp, tmp: importlib.import_module("agent.pet.store")._http_get(u, 5),
    "pet/store::_download": lambda u, mp, tmp: importlib.import_module("agent.pet.store")._download(
        u, tmp / "sheet.png", timeout=5),
    "pet/manifest::fetch_manifest": lambda u, mp, tmp: _fetch_manifest(u, mp),
    "tui_gateway/methods_images::_image_to_data_url": lambda u, mp, tmp: importlib.import_module(
        "tui_gateway.methods_images")._image_to_data_url(u, 1_000_000),
}


def _run(site, url, monkeypatch, tmp_path):
    """Return the body-bearing result, or None when the site refused (raised or returned None)."""
    try:
        return SITES[site](url, monkeypatch, tmp_path)
    except Exception:
        return None


@pytest.mark.parametrize("site", list(SITES))
def test_remote_fetch_sites_refuse_internal_targets_before_connect(site, listener, monkeypatch, tmp_path):
    from tools import url_safety

    base, hits = listener
    suffix = "/manifest.json" if "manifest" in site else "/img.png"

    # Direct loopback target: refused up front, listener never sees a connection.
    monkeypatch.delenv("HERMES_ALLOW_PRIVATE_URLS", raising=False)
    url_safety._reset_allow_private_cache()
    assert _run(site, base + suffix, monkeypatch, tmp_path) is None
    assert hits == []

    # Safe-looking first hop that 302s to the metadata endpoint: the hop is re-validated
    # (metadata stays blocked even when private URLs are allowed), so nothing is cached.
    monkeypatch.setenv("HERMES_ALLOW_PRIVATE_URLS", "1")
    url_safety._reset_allow_private_cache()
    try:
        assert _run(site, base + "/to-metadata" + suffix, monkeypatch, tmp_path) is None
    finally:
        monkeypatch.delenv("HERMES_ALLOW_PRIVATE_URLS", raising=False)
        url_safety._reset_allow_private_cache()
    assert hits == ["/to-metadata" + suffix]
    assert not list(Path(tmp_path / ".hermes").rglob("*.png")), "no body may be cached"
