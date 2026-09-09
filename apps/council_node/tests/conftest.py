"""Shared fixtures. Everything is built against tmp_path; no shared state."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.council_node.app.agents.registry import (  # noqa: E402
    AgentClass, AgentRecord, AgentRegistry, Authority,
)
from apps.council_node.app.governance.capabilities import (  # noqa: E402
    Capability, CapabilityRegistry,
)
from apps.council_node.app.governance.constitution import Constitution  # noqa: E402
from apps.council_node.app.governance.evaluator import PolicyEvaluator  # noqa: E402
from apps.council_node.app.governance.founder_gate import FounderGate  # noqa: E402
from apps.council_node.app.receipts.writer import ReceiptWriter  # noqa: E402

AUTHORITY = {
    "version": "1.0.0",
    "human_final_authority": "human_overseer",
    "default_behavior": "deny",
    "risk_levels": {
        "low": {"council_approvals_required": 0, "human_approval_required": False},
        "moderate": {"council_approvals_required": 2, "human_approval_required": False},
        "critical": {"council_approvals_required": 5, "human_approval_required": True},
        "prohibited": {
            "council_approvals_required": 5,
            "human_approval_required": True,
            "action": "reject",
        },
    },
    "independent_veto_domains": ["law_governance", "security_risk"],
    "actions": [
        {"id": "read.public", "risk": "low"},
        {"id": "publish.post", "risk": "moderate"},
        {"id": "money.transfer", "risk": "critical"},
        {"id": "data.destroy", "risk": "prohibited"},
    ],
}

COUNCIL = {
    "version": "2.0.0",
    "preserve_dissent": True,
    "proposer_may_not_be_sole_approver": True,
    "councils": [
        {"id": "truth_evidence", "veto": False},
        {"id": "law_governance", "veto": True},
        {"id": "security_risk", "veto": True},
        {"id": "engineering_reliability", "veto": False},
        {"id": "business_human_impact", "veto": False},
    ],
}


@pytest.fixture
def governance_dir(tmp_path: Path) -> Path:
    d = tmp_path / "governance"
    d.mkdir()
    (d / "authority_matrix.json").write_text(json.dumps(AUTHORITY), encoding="utf-8")
    (d / "five_council_policy.json").write_text(json.dumps(COUNCIL), encoding="utf-8")
    return d


@pytest.fixture
def constitution(governance_dir: Path) -> Constitution:
    return Constitution(governance_dir)


@pytest.fixture
def capabilities() -> CapabilityRegistry:
    return CapabilityRegistry({
        "read.public": Capability("read.public", "read", False, True),
        "publish.post": Capability("publish.post", "external", True, True),
        "money.transfer": Capability("money.transfer", "destructive", True, True),
        "data.destroy": Capability("data.destroy", "destructive", True, True),
        "disabled.cap": Capability("disabled.cap", "read", False, False),
    })


@pytest.fixture
def founder_gate(tmp_path: Path) -> FounderGate:
    return FounderGate("founder-token-for-tests", tmp_path / "holds.json")


@pytest.fixture
def evaluator(constitution, capabilities, founder_gate) -> PolicyEvaluator:
    return PolicyEvaluator(constitution, capabilities, founder_gate)


@pytest.fixture
def receipts(tmp_path: Path) -> ReceiptWriter:
    return ReceiptWriter(tmp_path / "receipts")


@pytest.fixture
def agents() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(AgentRecord(
        agent_id="worker-01", name="Worker", agent_class=AgentClass.WORKER,
        authority=Authority.EXECUTING,
        allowed_capabilities=("read.public", "publish.post", "money.transfer", "data.destroy"),
    ))
    registry.register(AgentRecord(
        agent_id="advisor-01", name="Advisor", agent_class=AgentClass.RESEARCHER,
        authority=Authority.ADVISORY,
        allowed_capabilities=("read.public",),
    ))
    return registry
