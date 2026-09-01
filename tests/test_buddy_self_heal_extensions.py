from pathlib import Path

import pytest

from buddy_core.core.brain_router import BrainResult
from buddy_core.core.operator import BuddyOperator
import buddy_core.core.operator as operator_module
import buddy_core.core.operator_extensions as extensions
import buddy_core.core.capability_health as capability_health
import buddy_core.core.self_heal as self_heal


class FakeBrain:
    def __call__(self, prompt, *, task_type="general", system=None, **kwargs):
        return BrainResult(
            text="verified",
            provider="test",
            model="fake",
            task_type=task_type,
            fallback_hops=0,
        )


def fake_research(query, max_sources=5):
    return {
        "query": query,
        "backend_status": "HEALTHY",
        "fetched_at": "2026-08-31T00:00:00Z",
        "independent_domains": 2,
        "errors": [],
        "truth_rule": "evidence only",
        "sources": [
            {"url": "https://example.com/a", "title": "A", "excerpt": "a", "status": 200, "quality": 0.8},
            {"url": "https://example.org/b", "title": "B", "excerpt": "b", "status": 200, "quality": 0.8},
        ],
    }


@pytest.fixture
def op(tmp_path, monkeypatch):
    monkeypatch.setattr(operator_module, "record_mission", lambda record: record)
    monkeypatch.setattr(operator_module, "audit", lambda event, data: {"event": event})
    monkeypatch.setattr(operator_module, "recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr(operator_module, "record_lesson", lambda *a, **k: {"record_hash": "lesson"})
    return BuddyOperator(
        researcher=fake_research,
        brain_call=FakeBrain(),
        state_dir=tmp_path,
        learning_cycle=lambda: {"learned": 1, "results": []},
    )


def test_extensions_are_installed_on_every_operator(op):
    expected = {
        "system.capability_health": "native:capability_health",
        "system.self_diagnose": "native:self_diagnose",
        "system.self_repair": "native:self_repair",
        "mcp.connectors_list": "native:mcp_list",
        "mcp.connector_invoke": "native:mcp_invoke",
    }
    for cap_id, executor in expected.items():
        assert cap_id in op.capabilities
        assert op.capabilities[cap_id]["executor"] == executor
        assert executor in op._executors


def test_fix_yourself_routes_to_diagnose_repair_and_reaudit(op, monkeypatch):
    monkeypatch.setattr(
        extensions,
        "diagnose",
        lambda: {"observed_at": "now", "healthy": False, "issues": [{"id": "x"}], "mcp_connectors": {"registered": 8, "failed": 1}},
    )
    monkeypatch.setattr(
        extensions,
        "repair_safe",
        lambda: {"status": "REPAIRED", "receipt": "/tmp/receipt.json", "authorization_id": "founder-safe-internal-self-heal-v1"},
    )
    monkeypatch.setattr(
        extensions,
        "audit_capabilities",
        lambda operator: {"status": "HEALTHY", "registered_enabled": 21, "native_connected": 16, "mcp": {"status": "HEALTHY"}},
    )

    result = op.handle("fix yourself", session_id="self-heal-test")
    assert result["status"] == "COMPLETE"
    assert [r["capability"] for r in result["receipts"]] == [
        "system.self_diagnose",
        "system.self_repair",
        "system.capability_health",
    ]
    assert all(r["status"] == "VERIFIED" for r in result["receipts"])


def test_blocked_self_heal_blocks_mission_instead_of_faking_complete(op, monkeypatch):
    monkeypatch.setattr(
        extensions,
        "diagnose",
        lambda: {"observed_at": "now", "healthy": False, "issues": [{"id": "x"}], "mcp_connectors": {"registered": 8, "failed": 1}},
    )
    monkeypatch.setattr(
        extensions,
        "repair_safe",
        lambda: {
            "status": "BLOCKED",
            "receipt": "/tmp/blocked.json",
            "authorization_id": "founder-safe-internal-self-heal-v1",
            "after": {"issues": [{"id": "still-broken"}]},
        },
    )
    result = op.handle("fix yourself")
    assert result["status"] == "BLOCKED"
    repair_receipt = next(r for r in result["receipts"] if r["capability"] == "system.self_repair")
    assert repair_receipt["status"] == "BLOCKED"


def test_capability_audit_is_direct_and_truthful(op, monkeypatch):
    monkeypatch.setattr(
        extensions,
        "audit_capabilities",
        lambda operator: {
            "status": "DEGRADED",
            "registered_enabled": 21,
            "native_connected": 16,
            "mcp": {"status": "UNAVAILABLE"},
        },
    )
    result = op.handle("check your capabilities")
    assert result["status"] == "COMPLETE"
    receipt = result["receipts"][0]
    assert receipt["capability"] == "system.capability_health"
    assert receipt["result"]["status"] == "DEGRADED"


def test_mcp_connector_executor_uses_registered_id_only(op, monkeypatch):
    monkeypatch.setattr(
        extensions.mcp_client,
        "list_connectors",
        lambda: {"connectors": [{"id": "n8n_health"}], "external_mutation_enabled": False},
    )
    monkeypatch.setattr(
        extensions.mcp_client,
        "invoke",
        lambda connector_id, params: {"connector_id": connector_id, "status": "PASS", "elapsed_ms": 1, "result": {"status": 200}},
    )
    result, evidence = op._executors["native:mcp_invoke"]("check n8n_health", {})
    assert result["connector_id"] == "n8n_health"
    assert evidence[0]["status"] == "PASS"

    with pytest.raises(extensions.OperatorExtensionError):
        op._executors["native:mcp_invoke"]("https://evil.example/run this", {})


def test_capability_health_merges_extension_registry(op, monkeypatch):
    monkeypatch.setattr(
        capability_health,
        "_mcp_health",
        lambda timeout=4.0: {"status": "HEALTHY", "connector_count": 8},
    )
    report = capability_health.audit_capabilities(op)
    assert report["extension_version"] == "1.0.0"
    assert report["native_missing"] == []
    assert report["status"] == "HEALTHY"
    assert report["registered_enabled"] == len(op.capabilities)


def test_self_heal_probes_every_registered_mcp_connector(monkeypatch):
    connector_ids = list(self_heal.MCP_REPAIR_MAP)
    monkeypatch.setattr(
        self_heal.mcp_client,
        "list_connectors",
        lambda: {
            "external_mutation_enabled": False,
            "connectors": [{"id": connector_id, "adapter": "http_get", "effect": "read_only"} for connector_id in connector_ids],
        },
    )
    calls = []

    def invoke(connector_id, params):
        calls.append(connector_id)
        if connector_id in {"radah_autopilot_timer", "revenue_runtime_service"}:
            return {"connector_id": connector_id, "status": "PASS", "elapsed_ms": 1, "result": {"returncode": 0}}
        return {"connector_id": connector_id, "status": "PASS", "elapsed_ms": 1, "result": {"status": 200}}

    monkeypatch.setattr(self_heal.mcp_client, "invoke", invoke)
    report = self_heal._mcp_connector_state()
    assert report["registered"] == len(connector_ids) == 8
    assert report["failed"] == 0
    assert report["all_healthy"] is True
    assert calls == connector_ids


def test_nonzero_exec_connector_is_failure_even_if_mcp_envelope_says_pass():
    healthy, evidence = self_heal._mcp_result_healthy({"status": "PASS", "result": {"returncode": 3}})
    assert healthy is False
    assert evidence == "exec_returncode"


def test_all_current_mcp_connectors_have_fixed_repair_targets():
    assert set(self_heal.MCP_REPAIR_MAP) == {
        "alpha_engine_health",
        "command_center_status",
        "conductor_health",
        "dominion_web_health",
        "n8n_health",
        "radah_autopilot_timer",
        "revenue_runtime_service",
        "wix_agent_health",
    }
    for target_kind, target in self_heal.MCP_REPAIR_MAP.values():
        if target_kind == "service":
            assert target in self_heal.SERVICE_RECIPES
        elif target_kind == "container":
            assert target in self_heal.CONTAINER_RECIPES
        else:
            pytest.fail(f"unexpected repair target kind: {target_kind}")


def test_container_repairs_are_fixed_names_only():
    expected = {
        "command_center": "dominion-command-center",
        "dominion_web": "dominion-web",
        "n8n": "n8n",
        "wix_agent": "wix-agent",
    }
    assert {name: spec["container"] for name, spec in self_heal.CONTAINER_RECIPES.items()} == expected


def test_self_heal_tracks_extension_and_registry_source_files():
    tracked = set(self_heal.TRACKED_RUNTIME_FILES)
    assert "core/__init__.py" in tracked
    assert "core/operator_extensions.py" in tracked
    assert "config/capability_registry.json" in tracked
    assert "config/capability_extensions.json" in tracked


def test_self_heal_protects_governance_and_forbids_arbitrary_shell():
    assert "config/BUDDY_CONSTITUTION.md" in self_heal.PROTECTED_GOVERNANCE_FILES
    assert "config/standing_authorizations.json" in self_heal.PROTECTED_GOVERNANCE_FILES
    source = Path(self_heal.__file__).read_text(encoding="utf-8")
    assert "shell=False" in source
    assert "shell=True" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_standing_authorization_explicitly_excludes_high_consequence_changes():
    auth_path = Path(self_heal.AUTH_FILE)
    text = auth_path.read_text(encoding="utf-8")
    assert "safe_internal_repair" in text
    assert "allowlisted fixed-name Dominion containers" in text
    assert "probe every registered governed read-only MCP connector" in text
    assert "change credentials" in text
    assert "change firewall rules" in text
    assert "spend or move money" in text
    assert "rewrite BUDDY_CONSTITUTION.md" in text
    assert "restart arbitrary containers" in text


def test_bridge_health_proves_extensions_and_self_heal_endpoint_exists():
    bridge = Path(__file__).resolve().parents[1] / "buddy_core" / "buddy_bridge_api.py"
    source = bridge.read_text(encoding="utf-8")
    assert 'self_heal_connected=self_heal_connected' in source
    assert 'mcp_operator_connected=mcp_connected' in source
    assert '@app.post("/webhook/buddy/self-heal")' in source
    assert 'get_operator().handle(' in source
    assert '"fix yourself"' in source
