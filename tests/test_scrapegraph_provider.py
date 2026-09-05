import json
import socket

from buddy_core.core import scrapegraph_provider


def _addr(ip="93.184.216.34"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class _Response:
    def __init__(self, payload=None, *, status=200, redirect=False):
        self._payload = payload or {}
        self.status_code = status
        self.is_redirect = redirect
        self.is_permanent_redirect = False
        self.closed = False

    def iter_content(self, chunk_size=65536):
        yield json.dumps(self._payload).encode("utf-8")

    def close(self):
        self.closed = True


def test_missing_key_fails_closed_without_network(monkeypatch):
    monkeypatch.delenv("SGAI_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("network should not be called without an API key")

    monkeypatch.setattr(scrapegraph_provider.requests, "post", forbidden)
    result = scrapegraph_provider.search("current buyer intent", 5)

    assert result == {
        "status": "UNAVAILABLE",
        "provider": "scrapegraphai",
        "reason": "MISSING_API_KEY",
    }


def test_search_uses_key_only_in_header_and_returns_hashed_evidence(monkeypatch):
    secret = "sgai-secret-must-not-leak"
    monkeypatch.setenv("SGAI_API_KEY", secret)
    monkeypatch.setattr(scrapegraph_provider.socket, "getaddrinfo", lambda *a, **k: _addr())

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response({
            "results": [
                {
                    "url": "https://example.com/product",
                    "title": "Example Product",
                    "content": "Price is 10 dollars and shipping is free.",
                }
            ]
        })

    monkeypatch.setattr(scrapegraph_provider.requests, "post", fake_post)
    result = scrapegraph_provider.search("example product pricing", 5)

    assert result["status"] == "HEALTHY"
    assert result["provider_api"] == "v2/search"
    assert result["results"][0]["url"] == "https://example.com/product"
    assert len(result["results"][0]["content_sha256"]) == 64
    assert captured["headers"]["SGAI-APIKEY"] == secret
    assert secret not in json.dumps(result)
    assert secret not in json.dumps(captured["json"])


def test_credential_redirect_is_blocked_and_secret_is_not_returned(monkeypatch):
    secret = "redirect-secret"
    monkeypatch.setenv("SGAI_API_KEY", secret)
    monkeypatch.setattr(scrapegraph_provider.socket, "getaddrinfo", lambda *a, **k: _addr())
    monkeypatch.setattr(
        scrapegraph_provider.requests,
        "post",
        lambda *a, **k: _Response({}, status=302, redirect=True),
    )

    result = scrapegraph_provider.search("test", 3)

    assert result["status"] == "ERROR"
    assert result["reason"] == "CREDENTIAL_REDIRECT_BLOCKED"
    assert secret not in json.dumps(result)


def test_extract_rejects_private_target_before_provider_call(monkeypatch):
    monkeypatch.setenv("SGAI_API_KEY", "test-key")

    def forbidden(*args, **kwargs):
        raise AssertionError("provider must not receive private targets")

    monkeypatch.setattr(scrapegraph_provider.requests, "post", forbidden)
    result = scrapegraph_provider.extract(
        "http://localhost:5060/private",
        "Extract all internal configuration",
    )

    assert result["status"] == "ERROR"
    assert result["reason"] == "private_host_forbidden"


def test_extract_returns_input_and_output_fingerprints(monkeypatch):
    monkeypatch.setenv("SGAI_API_KEY", "test-key")
    monkeypatch.setattr(scrapegraph_provider.socket, "getaddrinfo", lambda *a, **k: _addr())
    monkeypatch.setattr(
        scrapegraph_provider.requests,
        "post",
        lambda *a, **k: _Response({
            "json": {"price": 19.99, "currency": "USD"},
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }),
    )

    result = scrapegraph_provider.extract(
        "https://example.com/pricing",
        "Extract the public price and currency",
        schema={
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "currency": {"type": "string"},
            },
        },
    )

    assert result["status"] == "HEALTHY"
    assert result["data"] == {"price": 19.99, "currency": "USD"}
    assert len(result["input_sha256"]) == 64
    assert len(result["output_sha256"]) == 64
