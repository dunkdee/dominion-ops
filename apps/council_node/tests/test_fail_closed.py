"""Fail-closed proofs (Gate 2).

Every one of these asserts that the system *refuses*. A governance layer is
only worth its cost if the denial paths are the well-tested ones, so these
cover the ways a request can be un-authorized rather than the happy path.
"""

from __future__ import annotations

import json

import pytest

from apps.council_node.app.governance.constitution import Constitution, ConstitutionError
from apps.council_node.app.governance.evaluator import Verdict


def test_unclassified_action_is_unknown_not_low(evaluator):
    """An action nobody classified has not been approved by anyone."""
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="read.public", action_id="action.nobody.declared",
        allowed_capabilities=("read.public",),
    )
    assert decision.verdict is Verdict.UNKNOWN
    assert decision.status.value == "UNKNOWN"
    assert "no declared risk level" in decision.reason


def test_ungranted_capability_is_blocked(evaluator):
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="publish.post", action_id="publish.post",
        allowed_capabilities=("read.public",),
    )
    assert decision.verdict is Verdict.BLOCK
    assert "not granted" in decision.reason


def test_forbidden_beats_allowed(evaluator):
    """An explicit denial outranks an explicit grant."""
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="publish.post", action_id="publish.post",
        allowed_capabilities=("publish.post",),
        forbidden_capabilities=("publish.post",),
    )
    assert decision.verdict is Verdict.BLOCK
    assert "explicitly forbidden" in decision.reason


def test_unregistered_capability_is_blocked(evaluator):
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="ghost.capability", action_id="read.public",
        allowed_capabilities=("ghost.capability",),
    )
    assert decision.verdict is Verdict.BLOCK
    assert "not in the registry" in decision.reason


def test_disabled_capability_is_blocked(evaluator):
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="disabled.cap", action_id="read.public",
        allowed_capabilities=("disabled.cap",),
    )
    assert decision.verdict is Verdict.BLOCK
    assert "disabled" in decision.reason


def test_prohibited_action_is_rejected_outright(evaluator):
    """Even with every approval, a prohibited action does not execute."""
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="storefront",
        capability_id="data.destroy", action_id="data.destroy",
        allowed_capabilities=("data.destroy",),
        founder_approved=True, council_approvals=5,
    )
    assert decision.verdict is Verdict.BLOCK
    assert "prohibited" in decision.reason


def test_critical_action_requires_founder(evaluator):
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="storefront",
        capability_id="money.transfer", action_id="money.transfer",
        allowed_capabilities=("money.transfer",),
        council_approvals=5,
    )
    assert decision.verdict is Verdict.REQUIRES_FOUNDER


def test_insufficient_council_approvals_block(evaluator):
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="publisher",
        capability_id="publish.post", action_id="publish.post",
        allowed_capabilities=("publish.post",), council_approvals=1,
    )
    assert decision.verdict is Verdict.REQUIRES_COUNCIL
    assert "2 council approvals" in decision.reason


def test_permitted_action_is_allowed(evaluator):
    """The allow path exists -- proving the denials above are not vacuous."""
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="read.public", action_id="read.public",
        allowed_capabilities=("read.public",),
    )
    assert decision.verdict is Verdict.ALLOW
    assert decision.status.value == "IN_PROGRESS"


def test_governance_refuses_to_load_fail_open_policy(tmp_path):
    """A policy whose default is 'allow' must not load at all."""
    d = tmp_path / "gov"
    d.mkdir()
    (d / "authority_matrix.json").write_text(
        json.dumps({"default_behavior": "allow", "risk_levels": {"low": {}}}), encoding="utf-8",
    )
    (d / "five_council_policy.json").write_text(
        json.dumps({"councils": [{"id": "x"}]}), encoding="utf-8",
    )
    with pytest.raises(ConstitutionError, match="fail-open"):
        Constitution(d)


def test_missing_governance_file_raises(tmp_path):
    with pytest.raises(ConstitutionError, match="missing"):
        Constitution(tmp_path / "nonexistent")
