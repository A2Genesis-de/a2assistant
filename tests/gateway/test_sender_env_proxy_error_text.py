"""Env proxy selection for redaction (``HTTPS_PROXY`` / ``NO_PROXY``)."""

ENV_PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
_SECRET = "http://bob:qzxqzxqzx@127.0.0.1:1"


def test_an_oddly_cased_no_proxy_alone_is_not_a_bypass(monkeypatch):
    # httplib2 reads only ``no_proxy`` / ``NO_PROXY``: a ``No_Proxy`` it ignores cannot prove a direct send.
    from gateway.platforms.base_log_safety import env_proxy_for_redaction

    for name in (*ENV_PROXY_VARS, "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", _SECRET)
    monkeypatch.setenv("No_Proxy", "*")
    assert env_proxy_for_redaction("https://chat.googleapis.com") == _SECRET
    monkeypatch.setenv("NO_PROXY", "*")
    assert env_proxy_for_redaction("https://chat.googleapis.com") is None
