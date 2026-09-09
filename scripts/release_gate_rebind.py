#!/usr/bin/env python3
"""Generate the deterministic Dominion release-gate checkpoint for a PR head.

A code change must never inherit approval from a previous SHA. This helper makes that
state explicit and machine-readable so the PR workflow can immediately rebind the
gate to the new exact head instead of leaving operators to discover stale approval
manually.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

COUNCIL_ORDER = (
    "truth_evidence",
    "law_governance",
    "security_risk",
    "engineering_reliability",
    "business_human_impact",
)


@dataclass(frozen=True)
class GateCheckpoint:
    pr_number: int
    head_sha: str
    previous_sha: str | None
    stale_prior_authority: bool
    ci_status: str
    founder_authorization: str
    five_council: str
    next_action: str
    council_order: tuple[str, ...] = COUNCIL_ORDER


def build_checkpoint(*, pr_number: int, head_sha: str, previous_sha: str | None) -> GateCheckpoint:
    if not head_sha or len(head_sha) < 7:
        raise ValueError("head_sha is required")
    if pr_number <= 0:
        raise ValueError("pr_number must be positive")

    changed = bool(previous_sha and previous_sha != head_sha)
    return GateCheckpoint(
        pr_number=pr_number,
        head_sha=head_sha,
        previous_sha=previous_sha,
        stale_prior_authority=changed,
        ci_status="PENDING",
        founder_authorization="REQUIRED",
        five_council="REQUIRED",
        next_action="RUN_EXACT_HEAD_CI",
    )


def render_markdown(checkpoint: GateCheckpoint) -> str:
    stale = (
        f"Prior authorization/reviews bound to `{checkpoint.previous_sha}` are STALE by design."
        if checkpoint.stale_prior_authority
        else "No prior SHA was supplied; this head starts a fresh gate."
    )
    order = " → ".join(checkpoint.council_order)
    return f"""<!-- dominion-release-gate-state -->
## Dominion Release Gate — exact-head checkpoint

- PR: #{checkpoint.pr_number}
- Exact head: `{checkpoint.head_sha}`
- CI: **{checkpoint.ci_status}**
- Founder authorization: **{checkpoint.founder_authorization}**
- Five Council: **{checkpoint.five_council}**
- Next action: **{checkpoint.next_action}**

{stale}

Council order: `{order}`

**Invariant:** a head change never carries forward approval. The workflow automatically
rebinds the gate to the new SHA and exposes the next required action immediately.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--previous")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    checkpoint = build_checkpoint(pr_number=args.pr, head_sha=args.head, previous_sha=args.previous)
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as fh:
            json.dump(asdict(checkpoint), fh, indent=2)
            fh.write("\n")
    if args.markdown_output:
        with open(args.markdown_output, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(checkpoint))

    print(f"RELEASE_GATE_REBIND=PASS head={checkpoint.head_sha} stale={str(checkpoint.stale_prior_authority).lower()}")


if __name__ == "__main__":
    main()
