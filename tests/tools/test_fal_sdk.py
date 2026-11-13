"""FAL SDK adapters against the installed SDK; only HTTP leaves are replaced."""
import fal_client
import httpx
import pytest

from tools.fal_common import import_fal_client


@pytest.fixture
def transport(monkeypatch):
    requests, responses, clients = [], [], []
    original = httpx.Client.__init__

    def handle(request):
        assert request.url.host == "queue.test", "no external FAL requests allowed"
        requests.append(request)
        reply = responses.pop(0)
        if isinstance(reply, Exception):
            raise reply
        status, body = reply
        return httpx.Response(status, json=body)

    def initialize(client, *args, **kwargs):
        kwargs.update(transport=httpx.MockTransport(handle), trust_env=False)
        original(client, *args, **kwargs)
        clients.append(client)

    monkeypatch.setattr(httpx.Client, "__init__", initialize)
    # Keep the SDK retry algorithm, but do not spend wall time backing off.
    monkeypatch.setattr(fal_client.client.time, "sleep", lambda delay: None)
    yield requests, responses
    for client in clients:
        client.close()


@pytest.mark.parametrize("failure", [None, ImportError("external SDK"), RuntimeError("PM acquisition failed")])
def test_import_adapter_keeps_pm_failure_policy(monkeypatch, failure):
    import pm
    calls = []

    def ensure(feature):
        calls.append(feature)
        if failure:
            raise failure

    monkeypatch.setattr(pm, "ensure_import", ensure)
    if isinstance(failure, RuntimeError):
        with pytest.raises(ImportError, match="PM acquisition failed"):
            import_fal_client()
    else:
        assert import_fal_client() is fal_client
    assert calls == ["fal"]


def test_import_adapter_runs_real_pm_availability_without_install(monkeypatch):
    import pm.client
    monkeypatch.setattr(pm.client, "sync_venv", lambda *a, **kw: pytest.fail("available SDK must not install"))
    assert import_fal_client() is fal_client


def test_external_sdk_remains_importable_without_pm(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "pm", None)
    assert import_fal_client() is fal_client


def test_image_wait_polls_queue_status_at_gateway_cadence(transport, monkeypatch):
    """The SDK's ``handle.get()`` polls every 0.1 s; the wait drains status at FAL_QUEUE_POLL_SECONDS."""
    import tools.image_generation_tool as image_tool
    from tools.fal_common import FAL_QUEUE_POLL_SECONDS

    requests, replies = transport
    sleeps = []
    monkeypatch.setattr(fal_client.client.time, "sleep", sleeps.append)
    replies.extend([(200, {"status": "IN_QUEUE", "queue_position": 0}),
                    (200, {"status": "IN_PROGRESS", "logs": None}),
                    *[(200, {"status": "COMPLETED", "logs": None})] * 2, (200, {"images": ["done"]})])
    handle = fal_client.client.SyncRequestHandle(
        request_id="r1", response_url="https://queue.test/result", status_url="https://queue.test/status",
        cancel_url="https://queue.test/cancel", client=httpx.Client())
    assert image_tool._wait_fal_result(handle) == {"images": ["done"]}
    assert sleeps == [FAL_QUEUE_POLL_SECONDS] * 2
    assert [r.url.path for r in requests] == ["/status", "/status", "/status", "/status", "/result"]
