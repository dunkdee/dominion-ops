from types import SimpleNamespace

from buddy_core.core import capability_health


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise capability_health.requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


def test_capability_audit_reports_real_native_connections(monkeypatch):
    def fake_get(url, timeout=4.0):
        if url.endswith("/health"):
            return FakeResponse({
                "status": "ok",
                "service": "dominion-mcp-cli",
                "version": "1.0.0",
                "connector_count": 2,
                "external_mutation_enabled": False,
                "binding": "loopback-only",
            })
        return FakeResponse({
            "external_mutation_enabled": False,
            "connectors": [
                {"id": "a", "effect": "read_only", "adapter": "http_get"},
                {"id": "b", "effect": "read_only", "adapter": "exec"},
            ],
        })

    monkeypatch.setattr(capability_health.requests, "get", fake_get)

    # Load the declared native executor names so this test validates the audit
    # logic without starting network/model dependencies through BuddyOperator.
    registry = capability_health._load_registry()
    declared_native = {
        c["executor"]: object()
        for c in registry["capabilities"]
        if c.get("enabled", True) and str(c.get("executor", "")).startswith("native:")
    }
    operator = SimpleNamespace(_executors=declared_native)

    result = capability_health.audit_capabilities(operator)
    assert result["status"] == "HEALTHY"
    assert result["blocking_gaps"] == []
    assert result["native_missing"] == []
    assert result["mcp"]["status"] == "HEALTHY"
    assert result["mcp"]["connector_count"] == 2
    assert result["boundary_only"] >= 1


def test_capability_audit_fails_visible_on_missing_native_executor(monkeypatch):
    monkeypatch.setattr(
        capability_health,
        "_mcp_health",
        lambda: {"status": "HEALTHY", "connector_count": 0, "connectors": []},
    )
    operator = SimpleNamespace(_executors={})
    result = capability_health.audit_capabilities(operator)
    assert result["status"] == "DEGRADED"
    assert "native_executor_missing" in result["blocking_gaps"]
    assert result["native_missing"]


def test_capability_audit_marks_external_declarations_boundary_only(monkeypatch):
    monkeypatch.setattr(
        capability_health,
        "_mcp_health",
        lambda: {"status": "HEALTHY", "connector_count": 0, "connectors": []},
    )
    registry = capability_health._load_registry()
    declared_native = {
        c["executor"]: object()
        for c in registry["capabilities"]
        if c.get("enabled", True) and str(c.get("executor", "")).startswith("native:")
    }
    result = capability_health.audit_capabilities(SimpleNamespace(_executors=declared_native))
    ids = {item["id"] for item in result["external_boundaries"]}
    assert "external.publish" in ids
    assert "external.message" in ids
    assert "external.spend" in ids
    assert "external.submit" in ids
    assert "external.browser" in ids
    assert "external.credential_or_network" in ids


def test_mcp_url_must_remain_loopback(monkeypatch):
    monkeypatch.setattr(capability_health, "MCP_BASE_URL", "https://example.com")
    result = capability_health._mcp_health()
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "mcp_url_must_be_loopback"
