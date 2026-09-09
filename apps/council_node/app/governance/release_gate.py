"""Release gate — the Five Council decision.

Aggregation is fail-closed and mirrors the existing Dominion policy:

  VETO from a veto-domain council   blocks, alone
  HOLD                              blocks
  UNKNOWN                           blocks (rule 9: unknown stays unknown)
  a missing council                 blocks (silence is not consent)

Dissent is preserved. Automated checks may never be recorded as human
approval. The decision also exposes the exact ordered review queue so missing
Council work becomes an actionable control-plane item rather than a manual
bottleneck.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from .constitution import Constitution, Status


class CouncilVerdict(str, Enum):
    APPROVE = "APPROVE"
    HOLD = "HOLD"
    VETO = "VETO"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CouncilVote:
    council_id: str
    verdict: CouncilVerdict
    reason: str
    is_human: bool = False

    def to_dict(self) -> dict:
        return {
            "council_id": self.council_id,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "is_human": self.is_human,
        }


@dataclass(frozen=True)
class ReleaseDecision:
    released: bool
    status: Status
    reasons: tuple[str, ...]
    votes: tuple[CouncilVote, ...] = field(default_factory=tuple)
    dissent: tuple[CouncilVote, ...] = field(default_factory=tuple)
    pending_councils: tuple[str, ...] = field(default_factory=tuple)
    next_actions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "released": self.released,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "votes": [v.to_dict() for v in self.votes],
            "dissent": [v.to_dict() for v in self.dissent],
            "pending_councils": list(self.pending_councils),
            "next_actions": list(self.next_actions),
        }


class ReleaseGate:
    def __init__(self, constitution: Constitution) -> None:
        self.constitution = constitution

    def evaluate(
        self,
        votes: list[CouncilVote],
        *,
        require_human_approval: bool = False,
        proposer_council_id: str | None = None,
    ) -> ReleaseDecision:
        reasons: list[str] = []
        expected_order = tuple(self.constitution.council_ids)
        expected = set(expected_order)

        # Duplicate identities are ambiguous and must not be collapsed silently.
        counts = Counter(v.council_id for v in votes)
        duplicates = tuple(cid for cid in expected_order if counts[cid] > 1)
        for council_id in duplicates:
            reasons.append(
                f"council '{council_id}' submitted multiple reviews; ambiguous identity blocks release"
            )

        # Unknown identities can never satisfy a constitutional seat.
        unknown_ids = tuple(sorted(set(counts) - expected))
        for council_id in unknown_ids:
            reasons.append(f"unknown council identity '{council_id}' blocks release")

        by_council = {v.council_id: v for v in votes if v.council_id in expected}
        veto_domains = self.constitution.veto_councils

        # Preserve constitutional Council order so the control plane always knows
        # exactly which review is next; silence is not consent.
        missing = tuple(cid for cid in expected_order if cid not in by_council)
        for council_id in missing:
            reasons.append(f"council '{council_id}' did not report; missing review blocks release")

        blocking: list[CouncilVote] = []
        for vote in votes:
            if vote.council_id not in expected:
                continue
            if vote.verdict is CouncilVerdict.VETO:
                if vote.council_id in veto_domains:
                    reasons.append(f"'{vote.council_id}' VETO (independent veto domain): {vote.reason}")
                else:
                    reasons.append(f"'{vote.council_id}' VETO: {vote.reason}")
                blocking.append(vote)
            elif vote.verdict is CouncilVerdict.HOLD:
                reasons.append(f"'{vote.council_id}' HOLD: {vote.reason}")
                blocking.append(vote)
            elif vote.verdict is CouncilVerdict.UNKNOWN:
                reasons.append(f"'{vote.council_id}' returned UNKNOWN: {vote.reason}")
                blocking.append(vote)

        approvals = [
            v for v in votes
            if v.council_id in expected and v.verdict is CouncilVerdict.APPROVE
        ]
        if (
            self.constitution.proposer_may_not_be_sole_approver
            and proposer_council_id
            and len(approvals) == 1
            and approvals[0].council_id == proposer_council_id
        ):
            reasons.append(
                f"'{proposer_council_id}' proposed this release and is its only approver"
            )
            blocking.append(approvals[0])

        if require_human_approval and not any(v.is_human for v in approvals):
            reasons.append("human approval is required and no human approval was recorded")

        released = not reasons
        if released:
            status = Status.DONE
        elif missing or unknown_ids or duplicates or any(
            v.verdict is CouncilVerdict.UNKNOWN for v in votes
        ):
            status = Status.UNKNOWN
        elif any(v.verdict is CouncilVerdict.HOLD for v in votes):
            status = Status.HOLD
        else:
            status = Status.BLOCKED

        dissent = tuple(
            v for v in votes
            if v.council_id in expected and v.verdict is not CouncilVerdict.APPROVE
        )

        next_actions: list[str] = [f"REVIEW:{cid}" for cid in missing]
        if not missing:
            next_actions.extend(
                f"RESOLVE:{v.council_id}:{v.verdict.value}"
                for v in blocking
            )
        if duplicates:
            next_actions.extend(f"RESOLVE_DUPLICATE:{cid}" for cid in duplicates)
        if unknown_ids:
            next_actions.extend(f"REMOVE_UNKNOWN:{cid}" for cid in unknown_ids)
        if require_human_approval and not any(v.is_human for v in approvals):
            next_actions.append("RECORD_REQUIRED_HUMAN_APPROVAL")

        return ReleaseDecision(
            released=released,
            status=status,
            reasons=tuple(reasons) or ("all councils approved",),
            votes=tuple(votes),
            dissent=dissent if self.constitution.preserve_dissent else (),
            pending_councils=missing,
            next_actions=tuple(next_actions),
        )
