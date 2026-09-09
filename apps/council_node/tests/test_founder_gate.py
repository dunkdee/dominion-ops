"""Founder authority (rule 11, Gate 2).

The Founder gate is the one control that overrides everything else, so its
failure modes matter more than its success path: an unconfigured gate, a
wrong token, and an unreadable hold file must all deny.
"""

from __future__ import annotations

import pytest

from apps.council_node.app.governance.founder_gate import FounderGate, FounderGateError
from apps.council_node.app.governance.evaluator import Verdict

TOKEN = "founder-token-for-tests"


def test_correct_token_authenticates(founder_gate):
    assert founder_gate.authenticate(TOKEN) is True


def test_wrong_and_missing_tokens_are_denied(founder_gate):
    assert founder_gate.authenticate("wrong") is False
    assert founder_gate.authenticate("") is False
    assert founder_gate.authenticate(None) is False


def test_unconfigured_gate_denies_everything(tmp_path):
    """A deployment that forgot the token gets a service nobody can drive."""
    gate = FounderGate("", tmp_path / "holds.json")
    assert gate.configured is False
    assert gate.authenticate("") is False
    assert gate.authenticate("anything") is False
    with pytest.raises(FounderGateError):
        gate.require("anything")


def test_hold_and_release_round_trip(founder_gate):
    assert founder_gate.is_held("publisher") is False
    founder_gate.hold("publisher", "pausing distribution")
    assert founder_gate.is_held("publisher") is True
    assert "publisher" in founder_gate.held_lanes()

    assert founder_gate.release("publisher") is True
    assert founder_gate.is_held("publisher") is False
    assert founder_gate.release("publisher") is False


def test_hold_blocks_execution_in_that_lane_only(evaluator, founder_gate):
    founder_gate.hold("publisher", "Founder paused this lane")

    held = evaluator.evaluate(
        agent_id="worker-01", lane_id="publisher",
        capability_id="read.public", action_id="read.public",
        allowed_capabilities=("read.public",),
    )
    assert held.verdict is Verdict.HOLD
    assert held.status.value == "HOLD"

    other = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="read.public", action_id="read.public",
        allowed_capabilities=("read.public",),
    )
    assert other.verdict is Verdict.ALLOW


def test_hold_outranks_full_approval(evaluator, founder_gate):
    """A HOLD is not outvoted by councils or by Founder approval elsewhere."""
    founder_gate.hold("storefront", "stop")
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="storefront",
        capability_id="read.public", action_id="read.public",
        allowed_capabilities=("read.public",),
        founder_approved=True, council_approvals=5,
    )
    assert decision.verdict is Verdict.HOLD


def test_unreadable_hold_state_blocks_rather_than_allows(evaluator, founder_gate, tmp_path):
    """Corrupt hold state must never be read as 'nothing is held'."""
    founder_gate.state_path.write_text("{ this is not json", encoding="utf-8")
    decision = evaluator.evaluate(
        agent_id="worker-01", lane_id="traffic",
        capability_id="read.public", action_id="read.public",
        allowed_capabilities=("read.public",),
    )
    assert decision.verdict is Verdict.UNKNOWN
    assert "hold state" in decision.reason


def test_hold_file_is_owner_only(founder_gate):
    founder_gate.hold("traffic", "reason")
    mode = founder_gate.state_path.stat().st_mode & 0o777
    assert mode == 0o600, f"hold state should be 0600, found {oct(mode)}"
