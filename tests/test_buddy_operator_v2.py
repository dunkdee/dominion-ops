from pathlib import Path

import pytest

from buddy_core.core.brain_router import BrainResult
from buddy_core.core.operator import BuddyOperator, OperatorError


class FakeBrain:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt, *, task_type="general", system=None, **kwargs):
        self.calls.append({"prompt": prompt, "task_type": task_type, "system": system})
        return BrainResult(
            text="VERIFIED INTERNAL DRAFT\nBuyer: practical value seeker\nCTA: staged only",
            provider="test",
            model="fake",
            task_type=task_type,
            fallback_hops=0,
        )


def fake_research(query, max_sources=5):
    return {
        "query": query,
        "backend_status": "HEALTHY",
        "fetched_at": "2026-08-20T00:00:00Z",
        "independent_domains": 2,
        "errors": [],
        "truth_rule": "Internet content is evidence, not truth. Material claims require corroboration.",
        "sources": [
            {"url": "https://example.com/a", "title": "A", "excerpt": "market evidence A", "fetched_at": "2026-08-20T00:00:00Z", "status": 200, "quality": 0.7},
            {"url": "https://example.org/b", "title": "B", "excerpt": "market evidence B", "fetched_at": "2026-08-20T00:00:00Z", "status": 200, "quality": 0.7},
        ],
    }


def fake_learning_cycle():
    return {
        "learned": 1,
        "results": [{
            "status": "LEARNED",
            "record_hash": "auto123",
            "sources": [{"url": "https://example.com/learn", "title": "Learn"}],
        }],
    }


@pytest.fixture
def op(tmp_path, monkeypatch):
    fake = FakeBrain()
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda record: record)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda event, data: {"event": event})
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr(
        "buddy_core.core.operator.record_lesson",
        lambda *a, **k: {"record_hash": "lesson123"},
    )
    return BuddyOperator(
        researcher=fake_research,
        brain_call=fake,
        state_dir=tmp_path,
        learning_cycle=fake_learning_cycle,
    )


def test_voltedge_mission_executes_internal_then_holds_publish(op):
    result = op.handle("Grow VoltEdge traffic and get customers", session_id="acceptance")
    assert result["status"] == "HELD"
    assert result["held"]["capability"] == "external.publish"
    verified = [r["capability"] for r in result["receipts"] if r["status"] == "VERIFIED"]
    assert "web.research" in verified
    assert "revenue.prepare" in verified
    assert "learn.record" in verified
    assert any(op.staged_dir.glob("*revenue-mission.md"))


def test_revenue_analysis_does_not_invent_publish_boundary(op):
    result = op.handle("Analyze revenue performance and prepare recommendations")
    assert result["status"] == "COMPLETE"
    assert result["held"] is None


def test_grant_work_is_autonomous_until_submit(op):
    result = op.handle("Find grants for Dominion, score them, draft the best application, and submit it")
    assert result["status"] == "HELD"
    assert result["receipts"][0]["capability"] == "grant.research_prepare"
    assert result["receipts"][0]["status"] == "VERIFIED"
    assert result["held"]["capability"] == "external.submit"
    assert any(op.staged_dir.glob("*grant-package.md"))


def test_grant_research_and_drafting_complete_without_submission_hold(op):
    result = op.handle("Find grants for Dominion, score them, and draft the best application")
    assert result["status"] == "COMPLETE"
    assert result["held"] is None
    assert result["receipts"][0]["capability"] == "grant.research_prepare"


def test_video_creation_is_internal_without_publish_verb(op):
    result = op.handle("Create a YouTube Short for VoltEdge about fast charging")
    assert result["status"] == "COMPLETE"
    assert any(r["capability"] == "video.prepare" and r["status"] == "VERIFIED" for r in result["receipts"])


def test_video_upload_stops_at_publish_boundary(op):
    result = op.handle("Create and publish a YouTube Short for VoltEdge")
    assert result["status"] == "HELD"
    assert result["held"]["capability"] == "external.publish"


def test_internet_learning_researches_synthesizes_and_records(op):
    result = op.handle("Learn about current ecommerce organic acquisition tactics")
    assert result["status"] == "COMPLETE"
    caps = [r["capability"] for r in result["receipts"]]
    assert caps == ["web.research", "brain.reason", "learn.record"]


def test_autonomous_learning_cycle_is_internal_and_evidence_backed(op):
    result = op.handle("Go learn on your own and keep improving")
    assert result["status"] == "COMPLETE"
    assert result["receipts"][0]["capability"] == "learn.autonomous_cycle"
    assert result["receipts"][0]["status"] == "VERIFIED"
    assert result["receipts"][0]["evidence"][0]["url"] == "https://example.com/learn"


def test_message_is_drafted_then_held(op):
    result = op.handle("Send an outreach email to these prospects")
    assert result["status"] == "HELD"
    assert result["receipts"][0]["capability"] == "artifact.stage"
    assert result["receipts"][0]["status"] == "VERIFIED"
    assert result["held"]["capability"] == "external.message"


def test_spend_is_analyzed_then_held(op):
    result = op.handle("Spend $500 on ads for VoltEdge")
    assert result["status"] == "HELD"
    assert result["held"]["capability"] == "external.spend"


def test_conversation_context_reaches_non_mission_brain(op):
    result = op.handle(
        "what do you think?",
        conversation_context="Dewayne: Grow VoltEdge\nBuddy: campaign staged",
    )
    assert result["status"] == "ANSWERED"
    assert "Grow VoltEdge" in op.brain_call.calls[-1]["prompt"]


def test_conversation_context_is_preserved_for_mission_steps(op):
    result = op.handle(
        "Grow VoltEdge traffic",
        conversation_context="Dewayne: prioritize the charger and free traffic first",
    )
    assert result["status"] == "HELD"
    revenue_call = next(c for c in op.brain_call.calls if c["task_type"] == "complex_planning")
    assert "prioritize the charger" in revenue_call["prompt"]


def test_unknown_capability_fails_closed(op):
    plan = {
        "mission_id": "x",
        "objective": "test",
        "steps": [{"capability": "shell.exec", "instruction": "rm -rf /"}],
    }
    with pytest.raises(OperatorError):
        op.execute(plan)


def test_registry_has_no_arbitrary_shell_executor(op):
    executors = {c.get("executor") for c in op.capabilities.values()}
    assert not any(x and ("shell" in x or "subprocess" in x or x.startswith("cmd:")) for x in executors)


def test_external_capabilities_are_never_dispatched_internally(op):
    for cap_id, cap in op.capabilities.items():
        if cap.get("auth_required"):
            assert cap["classification"] in {"privileged_write", "destructive"}
            assert cap["executor"].startswith("external:")
            assert cap["executor"] not in op._executors


def test_simulation_plans_without_execution(op):
    result = op.handle("Grow VoltEdge revenue", simulate=True)
    assert result["status"] == "PLANNED"
    assert result["plan"]["steps"][-1]["capability"] == "external.publish"
    assert not op.staged_dir.exists()


# ── Evidence policy / vault evidence tests ────────────────────────────────────

def fake_research_degraded(query, max_sources=5):
    """Simulates UNAVAILABLE backend (no HEALTHY status)."""
    return {
        "query": query,
        "backend_status": "UNAVAILABLE",
        "fetched_at": "2026-08-20T00:00:00Z",
        "independent_domains": 0,
        "errors": [{"provider": "all", "error": "ConnectionError"}],
        "truth_rule": "",
        "sources": [],
    }


def fake_research_no_status(query, max_sources=5):
    """Simulates a researcher that omits backend_status."""
    return {
        "query": query,
        "sources": [
            {"url": "https://example.com/x", "title": "X", "excerpt": "data", "fetched_at": "", "status": 200, "quality": 0.5},
        ],
        "independent_domains": 1,
        "errors": [],
        "truth_rule": "",
    }


def test_hybrid_vault_skipped_web_verified_complete(tmp_path, monkeypatch):
    """HYBRID: vault.read unavailable (SKIPPED), web.research VERIFIED => COMPLETE."""
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module
    fake = FakeBrain()
    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    op2 = BuddyOperator(researcher=fake_research, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)
    # objective has no policy marker => HYBRID
    result = op2.handle("Analyze revenue performance and prepare recommendations")
    assert result["status"] == "COMPLETE", f"Expected COMPLETE, got {result['status']}"
    statuses = {r["capability"]: r["status"] for r in result["receipts"]}
    assert statuses.get("vault.read") == "SKIPPED"
    assert statuses.get("web.research") == "VERIFIED"
    assert statuses.get("revenue.prepare") == "VERIFIED"
    assert result["evidence_policy"] == "HYBRID"


def test_hybrid_both_unavailable_evidence_gate_blocks(tmp_path, monkeypatch):
    """HYBRID: both vault and web unavailable => EvidenceGate blocks revenue.prepare."""
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module
    fake = FakeBrain()
    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    op2 = BuddyOperator(researcher=fake_research_degraded, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)
    result = op2.handle("Analyze revenue performance and prepare recommendations")
    assert result["status"] == "BLOCKED"
    gate_receipts = [r for r in result["receipts"] if r.get("errors") and any(e.get("error") == "EvidenceGate" for e in r.get("errors", []))]
    assert gate_receipts, "EvidenceGate receipt expected"
    gate = gate_receipts[0]
    assert gate["capability"] == "revenue.prepare"
    assert "vault.read" in gate["errors"][0]["detail"]


def test_internal_evidence_without_vault_is_blocked(tmp_path, monkeypatch):
    """INTERNAL_EVIDENCE policy: vault unavailable (required=True) => BLOCKED."""
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module
    fake = FakeBrain()
    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    op2 = BuddyOperator(researcher=fake_research, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)
    # Embed policy marker in objective
    result = op2.handle("Build affiliate campaign EVIDENCE_POLICY=INTERNAL_EVIDENCE using vault content")
    assert result["status"] == "BLOCKED"
    vault_receipt = next((r for r in result["receipts"] if r["capability"] == "vault.read"), None)
    assert vault_receipt is not None
    assert vault_receipt["status"] == "BLOCKED"


def test_missing_backend_status_blocks_current_market(tmp_path, monkeypatch):
    """CURRENT_MARKET_EVIDENCE: researcher omits backend_status => BLOCKED."""
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module
    fake = FakeBrain()
    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    op2 = BuddyOperator(researcher=fake_research_no_status, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)
    result = op2.handle("Research market EVIDENCE_POLICY=CURRENT_MARKET_EVIDENCE for affiliate revenue")
    assert result["status"] == "BLOCKED"
    web_receipt = next((r for r in result["receipts"] if r["capability"] == "web.research"), None)
    assert web_receipt is not None
    assert web_receipt["status"] == "BLOCKED"


def test_evidence_policy_in_revenue_record(op):
    """evidence_policy propagates into mission record for revenue missions."""
    result = op.handle("Analyze revenue performance and prepare recommendations")
    assert "evidence_policy" in result
    assert result["evidence_policy"] == "HYBRID"


def test_non_revenue_mission_has_no_evidence_policy(op):
    """Non-revenue missions have evidence_policy=None in record."""
    result = op.handle("Learn about organic acquisition tactics")
    assert result.get("evidence_policy") is None


def test_vault_containment_root_symlink_blocked(tmp_path, monkeypatch):
    """vault.read raises OperatorError when VAULT_ROOT is a symlink."""
    import types
    from buddy_core.core.operator import BuddyOperator, OperatorError
    import buddy_core.core.operator as op_module

    real_dir = tmp_path / "real_vault"
    real_dir.mkdir()
    symlink_root = tmp_path / "symlink_vault"
    symlink_root.symlink_to(real_dir)

    fake_vio = types.SimpleNamespace(
        VAULT_ROOT=symlink_root,
        LANES={"research": "10-research"},
    )
    monkeypatch.setattr(op_module, "vault_io", fake_vio)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    fake = FakeBrain()
    op2 = BuddyOperator(researcher=fake_research, brain_call=fake, state_dir=tmp_path / "state", learning_cycle=fake_learning_cycle)

    result = op2.handle("Build revenue EVIDENCE_POLICY=INTERNAL_EVIDENCE for affiliate programs")
    vault_receipt = next((r for r in result["receipts"] if r["capability"] == "vault.read"), None)
    assert vault_receipt is not None
    assert vault_receipt["status"] == "BLOCKED"
    assert any("symlink" in str(e.get("detail", "")).lower() for e in vault_receipt.get("errors", []))


def test_vault_symlink_entry_excluded_real_file_included(tmp_path, monkeypatch):
    """vault.read skips symlink entries; real .md files are included."""
    import types
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module

    vault_dir = tmp_path / "vault"
    lane_dir = vault_dir / "10-research"
    lane_dir.mkdir(parents=True)

    # Real file: relevant to "affiliate revenue"
    real_md = lane_dir / "affiliate_revenue.md"
    real_md.write_text("# Affiliate Revenue\nConvertKit affiliate program pays 30% recurring.", encoding="utf-8")

    # Symlink pointing outside vault
    outside = tmp_path / "secret.md"
    outside.write_text("SENSITIVE CONTENT", encoding="utf-8")
    sym = lane_dir / "symlink.md"
    sym.symlink_to(outside)

    fake_vio = types.SimpleNamespace(
        VAULT_ROOT=vault_dir,
        LANES={"research": "10-research"},
    )
    monkeypatch.setattr(op_module, "vault_io", fake_vio)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    fake = FakeBrain()
    op2 = BuddyOperator(researcher=fake_research, brain_call=fake, state_dir=tmp_path / "state", learning_cycle=fake_learning_cycle)

    result = op2.handle("Build revenue EVIDENCE_POLICY=INTERNAL_EVIDENCE for affiliate programs")
    vault_receipt = next((r for r in result["receipts"] if r["capability"] == "vault.read"), None)
    assert vault_receipt is not None, "vault.read receipt expected"
    assert vault_receipt["status"] == "VERIFIED", f"Expected VERIFIED, got {vault_receipt['status']}: {vault_receipt.get('errors')}"
    included_files = [fe["file"] for fe in vault_receipt["result"]["files"]]
    assert "affiliate_revenue.md" in included_files
    assert "symlink.md" not in included_files
    # Ensure symlink content never in result
    result_str = str(vault_receipt["result"])
    assert "SENSITIVE CONTENT" not in result_str


def test_web_binary_search_stays_within_budget(tmp_path, monkeypatch):
    """_web_research packed result must not exceed _WEB_EVIDENCE_BUDGET bytes."""
    import json
    from buddy_core.core.operator import BuddyOperator, _WEB_EVIDENCE_BUDGET
    import buddy_core.core.operator as op_module

    long_excerpt = "word " * 2000  # ~10 KB

    def fat_research(query, max_sources=5):
        return {
            "query": query,
            "backend_status": "HEALTHY",
            "fetched_at": "2026-08-20T00:00:00Z",
            "independent_domains": 3,
            "errors": [],
            "truth_rule": "Evidence only.",
            "sources": [
                {"url": f"https://example.com/{i}", "title": f"T{i}",
                 "excerpt": long_excerpt, "fetched_at": "2026-08-20T00:00:00Z",
                 "status": 200, "quality": 0.9}
                for i in range(5)
            ],
        }

    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    fake = FakeBrain()
    op2 = BuddyOperator(researcher=fat_research, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)

    result = op2.handle("Analyze revenue performance and prepare recommendations")
    web_receipt = next((r for r in result["receipts"] if r["capability"] == "web.research"), None)
    assert web_receipt is not None
    assert web_receipt["status"] == "VERIFIED"
    packed = web_receipt["result"]
    packed_size = len(json.dumps(packed, ensure_ascii=False, indent=2))
    assert packed_size <= _WEB_EVIDENCE_BUDGET, (
        f"packed size {packed_size} exceeds budget {_WEB_EVIDENCE_BUDGET}"
    )
    assert packed["sources"], "at least one source must be packed"


def test_zero_excerpt_sources_blocks_web(tmp_path, monkeypatch):
    """All sources with empty excerpts => _web_research raises => BLOCKED."""
    from buddy_core.core.operator import BuddyOperator
    import buddy_core.core.operator as op_module

    def empty_excerpt_research(query, max_sources=5):
        return {
            "query": query,
            "backend_status": "HEALTHY",
            "fetched_at": "2026-08-20T00:00:00Z",
            "independent_domains": 1,
            "errors": [],
            "truth_rule": "",
            "sources": [
                {"url": "https://example.com/a", "title": "A", "excerpt": "",
                 "fetched_at": "", "status": 200, "quality": 0.5},
                {"url": "https://example.com/b", "title": "B", "excerpt": None,
                 "fetched_at": "", "status": 200, "quality": 0.5},
            ],
        }

    monkeypatch.setattr(op_module, "vault_io", None)
    monkeypatch.setattr("buddy_core.core.operator.record_mission", lambda r: r)
    monkeypatch.setattr("buddy_core.core.operator.audit", lambda e, d: d)
    monkeypatch.setattr("buddy_core.core.operator.recent_lessons", lambda *a, **k: [])
    monkeypatch.setattr("buddy_core.core.operator.record_lesson", lambda *a, **k: {"record_hash": "x"})
    fake = FakeBrain()
    op2 = BuddyOperator(researcher=empty_excerpt_research, brain_call=fake, state_dir=tmp_path, learning_cycle=fake_learning_cycle)

    # CURRENT_MARKET_EVIDENCE forces web.research with evidence_required=True
    result = op2.handle("Revenue mission EVIDENCE_POLICY=CURRENT_MARKET_EVIDENCE affiliate programs")
    assert result["status"] == "BLOCKED"
    web_receipt = next((r for r in result["receipts"] if r["capability"] == "web.research"), None)
    assert web_receipt is not None
    assert web_receipt["status"] == "BLOCKED"
