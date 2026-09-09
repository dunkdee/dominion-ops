"""Council release gate and constitutional loading (Gate 2, Gate 3)."""

from __future__ import annotations

from apps.council_node.app.agents.registry import (
    AgentClass, AgentRecord, AgentRegistry, AgentError, Authority,
)
from apps.council_node.app.governance.release_gate import (
    CouncilVerdict, CouncilVote, ReleaseGate,
)
import pytest

ALL = ("truth_evidence", "law_governance", "security_risk",
       "engineering_reliability", "business_human_impact")


def _approvals(*, human: tuple[str, ...] = ()) -> list[CouncilVote]:
    return [
        CouncilVote(c, CouncilVerdict.APPROVE, "ok", is_human=c in human) for c in ALL
    ]


def test_unanimous_approval_releases(constitution):
    decision = ReleaseGate(constitution).evaluate(_approvals())
    assert decision.released is True
    assert decision.status.value == "DONE"


def test_single_veto_from_veto_domain_blocks(constitution):
    votes = _approvals()
    votes[2] = CouncilVote("security_risk", CouncilVerdict.VETO, "credential exposure")
    decision = ReleaseGate(constitution).evaluate(votes)
    assert decision.released is False
    assert decision.status.value == "BLOCKED"
    assert any("independent veto domain" in r for r in decision.reasons)


def test_unknown_blocks_and_is_reported_as_unknown(constitution):
    votes = _approvals()
    votes[0] = CouncilVote("truth_evidence", CouncilVerdict.UNKNOWN, "cannot verify sources")
    decision = ReleaseGate(constitution).evaluate(votes)
    assert decision.released is False
    assert decision.status.value == "UNKNOWN"


def test_hold_blocks(constitution):
    votes = _approvals()
    votes[4] = CouncilVote("business_human_impact", CouncilVerdict.HOLD, "pricing unclear")
    decision = ReleaseGate(constitution).evaluate(votes)
    assert decision.released is False
    assert decision.status.value == "HOLD"


def test_missing_council_blocks_silence_is_not_consent(constitution):
    votes = _approvals()[:-1]
    decision = ReleaseGate(constitution).evaluate(votes)
    assert decision.released is False
    assert decision.status.value == "UNKNOWN"
    assert any("did not report" in r for r in decision.reasons)


def test_dissent_is_preserved(constitution):
    votes = _approvals()
    votes[1] = CouncilVote("law_governance", CouncilVerdict.VETO, "unlicensed claim")
    decision = ReleaseGate(constitution).evaluate(votes)
    assert len(decision.dissent) == 1
    assert decision.dissent[0].reason == "unlicensed claim"
    # The full ballot survives too, so the record shows who approved.
    assert len(decision.votes) == 5


def test_machine_votes_cannot_satisfy_human_approval(constitution):
    decision = ReleaseGate(constitution).evaluate(_approvals(), require_human_approval=True)
    assert decision.released is False
    assert any("human approval is required" in r for r in decision.reasons)


def test_human_approval_satisfies_the_requirement(constitution):
    decision = ReleaseGate(constitution).evaluate(
        _approvals(human=("law_governance",)), require_human_approval=True,
    )
    assert decision.released is True


def test_proposer_may_not_be_sole_approver(constitution):
    votes = [CouncilVote("truth_evidence", CouncilVerdict.APPROVE, "mine is fine")]
    decision = ReleaseGate(constitution).evaluate(
        votes, proposer_council_id="truth_evidence",
    )
    assert decision.released is False
    assert any("only approver" in r for r in decision.reasons)


# ── agent registry ──────────────────────────────────────────────────────

def test_agent_cannot_grant_itself_forbidden_capabilities():
    registry = AgentRegistry()
    with pytest.raises(AgentError, match="universally forbidden"):
        registry.register(AgentRecord(
            agent_id="rogue", name="Rogue", agent_class=AgentClass.WORKER,
            allowed_capabilities=("read.public", "shell.unrestricted"),
        ))


def test_agent_must_declare_radah_memshalah():
    registry = AgentRegistry()
    with pytest.raises(AgentError, match="governance"):
        registry.register(AgentRecord(
            agent_id="ungoverned", name="Ungoverned", agent_class=AgentClass.WORKER,
            governance="SOMETHING_ELSE",
        ))


def test_universal_denials_are_added_to_every_agent(agents):
    worker = agents.require("worker-01")
    forbidden = agents.effective_forbidden(worker)
    assert "secret_readback" in forbidden
    assert "financial_transfer" in forbidden


def test_disabled_agent_cannot_be_required():
    registry = AgentRegistry()
    registry.register(AgentRecord(
        agent_id="off", name="Off", agent_class=AgentClass.WORKER, enabled=False,
    ))
    with pytest.raises(AgentError, match="disabled"):
        registry.require("off")


def test_advisory_agents_may_not_execute(agents):
    assert agents.require("advisor-01").may_execute is False
    assert agents.require("worker-01").may_execute is True


def test_policy_revision_changes_when_governance_changes(constitution, governance_dir):
    from apps.council_node.app.governance.constitution import Constitution
    before = constitution.revision
    path = governance_dir / "authority_matrix.json"
    data = path.read_text(encoding="utf-8").replace('"low"', '"lowered"', 1)
    path.write_text(data, encoding="utf-8")
    assert Constitution(governance_dir).revision != before
