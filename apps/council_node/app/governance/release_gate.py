"""Release gate — the Five Council decision.

Aggregation is fail-closed and mirrors the existing Dominion policy:

  VETO from a veto-domain council   blocks, alone
  HOLD                              blocks
  UNKNOWN                           blocks (rule 9: unknown stays unknown)
  a missing council                 blocks (silence is not consent)

Dissent is preserved: the result carries every vote and every reason, so a
minority objection survives into the record rather than being averaged away.

An automated check may never be recorded as a human approval. Votes carry
`is_human`, and where the constitution requires human approval an all-machine
ballot cannot satisfy it.
"""

from __future__ import annotations

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

    def to_dict(self) -> dict:
        return {
            "released": self.released,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "votes": [v.to_dict() for v in self.votes],
            "dissent": [v.to_dict() for v in self.dissent],
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
        by_council = {v.council_id: v for v in votes}
        expected = set(self.constitution.council_ids)
        veto_domains = self.constitution.veto_councils

        # Silence is not consent.
        missing = sorted(expected - set(by_council))
        for council_id in missing:
            reasons.append(f"council '{council_id}' did not report; missing review blocks release")

        blocking: list[CouncilVote] = []
        for vote in votes:
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

        # A proposer cannot be its own sole approver.
        approvals = [v for v in votes if v.verdict is CouncilVerdict.APPROVE]
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

        # Human approval cannot be satisfied by machine votes.
        if require_human_approval and not any(v.is_human for v in approvals):
            reasons.append("human approval is required and no human approval was recorded")

        released = not reasons
        if released:
            status = Status.DONE
        elif any(v.verdict is CouncilVerdict.UNKNOWN for v in votes) or missing:
            status = Status.UNKNOWN
        elif any(v.verdict is CouncilVerdict.HOLD for v in votes):
            status = Status.HOLD
        else:
            status = Status.BLOCKED

        dissent = tuple(v for v in votes if v.verdict is not CouncilVerdict.APPROVE)
        return ReleaseDecision(
            released=released,
            status=status,
            reasons=tuple(reasons) or ("all councils approved",),
            votes=tuple(votes),
            dissent=dissent if self.constitution.preserve_dissent else (),
        )
