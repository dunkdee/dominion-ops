import socket

import pytest

from buddy_core.core import web_research


def _addr(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


def test_rejects_localhost(monkeypatch):
    with pytest.raises(ValueError):
        web_research._public_host("http://localhost/admin")


def test_rejects_private_resolved_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("10.0.0.5"))
    with pytest.raises(ValueError):
        web_research._public_host("https://internal.example")


def test_rejects_link_local_cloud_metadata(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("169.254.169.254"))
    with pytest.raises(ValueError):
        web_research._public_host("http://metadata.example/latest")


def test_rejects_credentials_in_url(monkeypatch):
    with pytest.raises(ValueError):
        web_research._public_host("https://user:pass@example.com/")


def test_allows_public_https(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addr("93.184.216.34"))
    web_research._public_host("https://example.com/research")


def test_search_transport_is_get_only_by_construction():
    # The research module exports no submit/post helper. Remote interaction is
    # deliberately limited to search/fetch reads; interactive browser work is
    # represented as a separate external capability in the operator registry.
    assert hasattr(web_research, "search")
    assert hasattr(web_research, "fetch_public_page")
    assert not hasattr(web_research, "post")
    assert not hasattr(web_research, "submit")


class TestWebBackendStatus:
    """research() must return correct backend_status for each provider path."""

    # ── Fixtures / helpers ────────────────────────────────────────────────────

    SERPAPI_TITLE   = "DISCOVERY_TITLE_MUST_NOT_BECOME_EVIDENCE"
    SERPAPI_SNIPPET = "DISCOVERY_SNIPPET_MUST_NOT_BECOME_EVIDENCE"
    TEST_KEY        = "fake_serpapi_secret_for_test"
    FETCHED_TITLE   = "Governed Fetched Title"
    FETCHED_CONTENT = "Governed fetched page content"

    def _make_ok_source(self, url):
        from buddy_core.core.web_research import Source
        return Source(
            url=url,
            title=self.FETCHED_TITLE,
            excerpt=self.FETCHED_CONTENT,
            fetched_at="2026-08-21T00:00:00Z",
            status=200,
            quality=0.9,
        )

    def _fail_fetch(self, url):
        raise ValueError("governed fetch failed")

    # ── Provider A: SerpAPI ───────────────────────────────────────────────────

    def test_serpapi_discovery_metadata_excluded_from_evidence(self, monkeypatch):
        """SerpAPI title/snippet are discovery-only; governed fetch provides evidence."""
        import json

        fetched_urls = []

        def spy_fetch(url):
            fetched_urls.append(url)
            return self._make_ok_source(url)

        monkeypatch.setenv("SERPAPI_KEY", self.TEST_KEY)
        monkeypatch.setattr(
            "buddy_core.core.web_research._serpapi_search",
            lambda q, limit=6: [
                {"url": "https://example.com/page",
                 "title": self.SERPAPI_TITLE,
                 "snippet": self.SERPAPI_SNIPPET},
            ],
        )
        monkeypatch.setattr("buddy_core.core.web_research.fetch_public_page", spy_fetch)
        monkeypatch.setattr("buddy_core.core.web_research.search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test query serpapi isolation")

        # Backend must be HEALTHY — unconditional
        assert result["backend_status"] == "HEALTHY"

        # Governed URL fetched
        assert fetched_urls == ["https://example.com/page"]

        # Source content comes from fetch_public_page, not from SerpAPI metadata
        source = result["sources"][0]
        assert source["title"]   == self.FETCHED_TITLE
        assert source["excerpt"] == self.FETCHED_CONTENT
        assert source["status"]  == 200
        assert source["quality"] == 0.9

        # Discovery metadata must NEVER appear in serialized result
        serialized = json.dumps(result)
        assert self.SERPAPI_TITLE   not in serialized
        assert self.SERPAPI_SNIPPET not in serialized
        assert self.TEST_KEY        not in serialized

    def test_serpapi_fetch_failure_yields_unavailable(self, monkeypatch):
        """SerpAPI candidate fetch fails; DDG also empty => UNAVAILABLE."""
        import json

        monkeypatch.setenv("SERPAPI_KEY", self.TEST_KEY)
        monkeypatch.setattr(
            "buddy_core.core.web_research._serpapi_search",
            lambda q, limit=6: [
                {"url": "https://example.com/page",
                 "title": self.SERPAPI_TITLE,
                 "snippet": self.SERPAPI_SNIPPET},
            ],
        )
        monkeypatch.setattr("buddy_core.core.web_research.fetch_public_page", self._fail_fetch)
        monkeypatch.setattr("buddy_core.core.web_research.search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test serpapi fetch failure")

        assert result["backend_status"] != "HEALTHY"
        assert result["backend_status"] == "UNAVAILABLE"

        serialized = json.dumps(result)
        assert self.SERPAPI_SNIPPET not in serialized
        assert self.TEST_KEY        not in serialized

    def test_serpapi_success_does_not_require_ddg(self, monkeypatch):
        """When SerpAPI yields a successfully fetched candidate, DDG HTML is not needed."""
        ddg_called = []

        def spy_ddg(query, limit=6):
            ddg_called.append(query)
            return []

        monkeypatch.setenv("SERPAPI_KEY", self.TEST_KEY)
        monkeypatch.setattr(
            "buddy_core.core.web_research._serpapi_search",
            lambda q, limit=6: [
                {"url": "https://example.com/serpapi-only",
                 "title": self.SERPAPI_TITLE,
                 "snippet": self.SERPAPI_SNIPPET},
            ],
        )
        monkeypatch.setattr(
            "buddy_core.core.web_research.fetch_public_page",
            self._make_ok_source,
        )
        monkeypatch.setattr("buddy_core.core.web_research.search", spy_ddg)
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test serpapi preference")

        assert result["backend_status"] == "HEALTHY"
        assert ddg_called == [], (
            f"DDG HTML was called despite successful SerpAPI fetch: {ddg_called}"
        )

    # ── Provider B: DDG HTML ──────────────────────────────────────────────────

    def test_healthy_on_successful_ddg_fetch(self, monkeypatch):
        """DDG HTML path: successful governed fetch => HEALTHY."""
        monkeypatch.setattr("buddy_core.core.web_research._serpapi_search", lambda *a, **k: [])
        monkeypatch.setattr(
            "buddy_core.core.web_research.search",
            lambda q, limit=6: [{"url": "https://example.com/ddg", "title": "DDG"}],
        )
        monkeypatch.setattr(
            "buddy_core.core.web_research.fetch_public_page",
            self._make_ok_source,
        )
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test ddg healthy")
        assert result["backend_status"] == "HEALTHY"
        assert result["sources"]
        assert result["sources"][0]["excerpt"] != ""

    def test_failed_fetch_not_healthy(self, monkeypatch):
        """All fetch attempts fail: result is not HEALTHY."""
        monkeypatch.setattr("buddy_core.core.web_research._serpapi_search", lambda *a, **k: [])
        monkeypatch.setattr(
            "buddy_core.core.web_research.search",
            lambda q, limit=6: [{"url": "https://example.com/page", "title": "T"}],
        )
        monkeypatch.setattr("buddy_core.core.web_research.fetch_public_page", self._fail_fetch)
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test failed fetch")
        assert result["backend_status"] != "HEALTHY"

    # ── Provider C: DDG JSON (DEGRADED) ───────────────────────────────────────

    def test_degraded_when_only_ddg_json(self, monkeypatch):
        """Only DDG JSON returns results: DEGRADED, sources have status=0, empty excerpt."""
        monkeypatch.setattr("buddy_core.core.web_research._serpapi_search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research.search", lambda *a, **k: [])
        monkeypatch.setattr(
            "buddy_core.core.web_research._ddg_json_search",
            lambda q, limit=6: [{"url": "https://example.com/ddgjson", "title": "DDG JSON"}],
        )

        from buddy_core.core.web_research import research
        result = research("test degraded ddg json")
        assert result["backend_status"] == "DEGRADED"
        assert result["sources"]
        assert result["sources"][0]["status"]  == 0
        assert result["sources"][0]["quality"] == 0.0
        assert result["sources"][0]["excerpt"] == ""

    def test_degraded_not_promoted_to_healthy(self, monkeypatch):
        """DEGRADED result must never have backend_status=HEALTHY."""
        monkeypatch.setattr("buddy_core.core.web_research._serpapi_search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research.search", lambda *a, **k: [])
        monkeypatch.setattr(
            "buddy_core.core.web_research._ddg_json_search",
            lambda q, limit=6: [
                {"url": "https://a.example.com/x", "title": "A"},
                {"url": "https://b.example.com/y", "title": "B"},
            ],
        )

        from buddy_core.core.web_research import research
        result = research("test degrade not promoted")
        assert result["backend_status"] == "DEGRADED"
        assert result["backend_status"] != "HEALTHY"

    # ── Provider D: UNAVAILABLE ───────────────────────────────────────────────

    def test_unavailable_when_all_providers_fail(self, monkeypatch):
        """All providers yield nothing: UNAVAILABLE, empty sources list."""
        monkeypatch.setattr("buddy_core.core.web_research._serpapi_search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research.search", lambda *a, **k: [])
        monkeypatch.setattr("buddy_core.core.web_research._ddg_json_search", lambda *a, **k: [])

        from buddy_core.core.web_research import research
        result = research("test fully unavailable")
        assert result["backend_status"] == "UNAVAILABLE"
        assert result["sources"] == []
