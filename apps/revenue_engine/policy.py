from __future__ import annotations

from dataclasses import dataclass

from .models import ActionDecision, normalize_evidence_refs


ALLOWED_SIMULATION_ACTIONS = frozenset(
    {
        "analyze_funnel",
        "draft_offer",
        "prepare_experiment",
        "measure_metrics",
        "rank_opportunities",
        "build_site_plan",
        "review_content",
        "propose_learning_change",
    }
)

PROHIBITED_ACTIONS = frozenset(
    {
        "publish_external_content",
        "contact_customer",
        "spend_or_move_money",
        "claim_guaranteed_income",
        "enroll_affiliate_program",
        "change_price",
        "activate_revenue_wave",
        "deploy_production",
    }
)


@dataclass(frozen=True)
class PolicyResult:
    action: str
    decision: ActionDecision
    reason: str
    evidence_refs: tuple[str, ...]


def evaluate_action(action: str, evidence_refs: tuple[str, ...] = ()) -> PolicyResult:
    action = action.strip()
    refs = normalize_evidence_refs(evidence_refs)
    if not action:
        return PolicyResult(
            action=action,
            decision=ActionDecision.BLOCKED,
            reason="Default deny: empty action.",
            evidence_refs=refs,
        )
    if action in PROHIBITED_ACTIONS:
        return PolicyResult(
            action=action,
            decision=ActionDecision.BLOCKED,
            reason=(
                "Blocked by the revenue_operations simulation boundary. "
                "Consequential external execution requires separate human/governance release."
            ),
            evidence_refs=refs,
        )
    if action not in ALLOWED_SIMULATION_ACTIONS:
        return PolicyResult(
            action=action,
            decision=ActionDecision.BLOCKED,
            reason="Default deny: action is not explicitly allowlisted for revenue simulation.",
            evidence_refs=refs,
        )
    return PolicyResult(
        action=action,
        decision=ActionDecision.SIMULATION_ONLY,
        reason="Allowed only as deterministic analysis/drafting; no external side effect is authorized.",
        evidence_refs=refs,
    )
