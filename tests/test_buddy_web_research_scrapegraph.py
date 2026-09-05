import json

from buddy_core.core import web_research


def test_scrapegraph_is_preferred_when_configured(monkeypatch):
    monkeypatch.setenv("SGAI_API_KEY", "configured-key")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(web_research, "_public_host", lambda url: None)
    monkeypatch.setattr(
        web_research.scrapegraph_provider,
        "search",
        lambda query, limit=6: {
            "status": "HEALTHY",
            "provider": "scrapegraphai",
            "observed_at": "2026-09-05T12:00:00+00:00",
            "results": [
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "content": "Evidence A",
                    "fetched_at": "2026-09-05T12:00:00+00:00",
                    "content_sha256": "a" * 64,
                },
                {
                    "url": "https://second.example/b",
                    "title": "B",
                    "content": "Evidence B",
                    "fetched_at": "2026-09-05T12:00:00+00:00",
                    "content_sha256": "b" * 64,
                },
            ],
        },
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("fallback provider should not run after healthy ScrapeGraph evidence")

    monkeypatch.setattr(web_research, "_serpapi_search", forbidden)
    monkeypatch.setattr(web_research, "search", forbidden)
    monkeypatch.setattr(web_research, "_ddg_json_search", forbidden)

    result = web_research.research("current competitor pricing", max_sources=5)

    assert result["backend_status"] == "HEALTHY"
    assert result["independent_domains"] == 2
    assert result["sources"][0]["provider"] == "scrapegraphai"
    assert result["sources"][0]["excerpt"] == "Evidence A"
    assert result["sources"][0]["content_sha256"] == "a" * 64


def test_scrapegraph_error_falls_back_without_leaking_key(monkeypatch):
    secret = "configured-key-that-must-not-leak"
    monkeypatch.setenv("SGAI_API_KEY", secret)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(
        web_research.scrapegraph_provider,
        "search",
        lambda *a, **k: {
            "status": "ERROR",
            "provider": "scrapegraphai",
            "reason": "PROVIDER_HTTP_429",
        },
    )
    monkeypatch.setattr(web_research, "_serpapi_search", lambda *a, **k: [])
    monkeypatch.setattr(web_research, "search", lambda *a, **k: [])
    monkeypatch.setattr(web_research, "_ddg_json_search", lambda *a, **k: [])

    result = web_research.research("current competitor pricing", max_sources=5)

    assert result["backend_status"] == "UNAVAILABLE"
    assert result["sources"] == []
    assert result["errors"][0] == {
        "provider": "scrapegraphai",
        "error": "PROVIDER_HTTP_429",
    }
    assert secret not in json.dumps(result)


def test_scrapegraph_private_source_is_rejected(monkeypatch):
    monkeypatch.setenv("SGAI_API_KEY", "configured-key")
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.setattr(
        web_research.scrapegraph_provider,
        "search",
        lambda *a, **k: {
            "status": "HEALTHY",
            "provider": "scrapegraphai",
            "results": [
                {
                    "url": "http://localhost/private",
                    "title": "Private",
                    "content": "should never become evidence",
                }
            ],
        },
    )
    monkeypatch.setattr(web_research, "_serpapi_search", lambda *a, **k: [])
    monkeypatch.setattr(web_research, "search", lambda *a, **k: [])
    monkeypatch.setattr(web_research, "_ddg_json_search", lambda *a, **k: [])

    result = web_research.research("test", max_sources=5)

    assert result["backend_status"] == "UNAVAILABLE"
    assert result["sources"] == []
    assert result["errors"][0]["provider"] == "scrapegraphai"
    assert result["errors"][0]["error"] == "PublicHostRejected"
