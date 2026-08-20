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
        "sources": [
            {"url": "https://example.com/a", "title": "A", "excerpt": "market evidence A", "fetched_at": "2026-08-20T00:00:00Z", "quality": 0.7},
            {"url": "https://example.org/b", "title": "B", "excerpt": "market evidence B", "fetched_at": "2026-08-20T00:00:00Z", "quality": 0.7},
        ],
        "independent_domains": 2,
        "errors": [],
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
