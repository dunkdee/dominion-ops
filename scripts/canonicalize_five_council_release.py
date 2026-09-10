#!/usr/bin/env python3
"""Prepare and finalize a canonical Five Council main-branch release record."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNCIL_NODE_COMPLIANCE = ROOT / "governance/council_node_release_compliance.json"
MAX_REVIEW_DIFF_BYTES = 120_000
# When this file is executed as `python3 scripts/...`, Python puts `scripts/`
# first on sys.path. That shadows the real top-level `control_plane` package with
# `scripts/control_plane.py`. Force the repository root to precedence so imports
# resolve to the canonical package.
root_str = str(ROOT)
if sys.path[0] != root_str:
    sys.path.insert(0, root_str)

from control_plane.canonical import sha256_json
from control_plane.final_release import evaluate_final_release

ORDER = (
    "truth_evidence",
    "law_governance",
    "security_risk",
    "engineering_reliability",
    "business_human_impact",
)


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path: str | Path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def hash_without(record: dict, field: str) -> str:
    return sha256_json({k: v for k, v in record.items() if k != field})


def _council_node_release(changed_files: list[str]) -> bool:
    """Return True only when the candidate actually changes Council Node scope."""
    prefixes = (
        "apps/council_node/",
        "deploy/council-node/",
        "deploy/systemd/dominion-council",
    )
    exact = {
        "governance/council_node_release_compliance.json",
        "governance/council_node_scope.json",
    }
    return any(path in exact or path.startswith(prefixes) for path in changed_files)


def _release_specific_evidence(changed_files: list[str]) -> dict[str, dict]:
    """Load only explicit, changed release evidence records from governance/."""
    records: dict[str, dict] = {}
    for rel in changed_files:
        path = Path(rel)
        name = path.name.lower()
        if not rel.startswith("governance/") or path.suffix.lower() != ".json":
            continue
        if "release_evidence" not in name and "release_compliance" not in name:
            continue
        candidate = ROOT / rel
        if candidate.is_file():
            records[rel] = load(candidate)
    return records


def _candidate_review_diff() -> dict:
    """Return a bounded exact candidate diff for independent Council inspection.

    Five Council decisions must not be based only on filenames and green checks.
    The gate is intentionally fail-closed for oversized changes: large releases
    must be split so the entire reviewed diff fits in the canonical evidence packet.
    """
    command = [
        "git",
        "diff",
        "--no-ext-diff",
        "--unified=20",
        "origin/main...HEAD",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode != 0:
        return {
            "available": False,
            "base": "origin/main",
            "reason": "git_diff_unavailable",
        }
    encoded = completed.stdout.encode("utf-8")
    if len(encoded) > MAX_REVIEW_DIFF_BYTES:
        raise SystemExit(
            f"candidate review diff too large for complete Council review: "
            f"{len(encoded)}>{MAX_REVIEW_DIFF_BYTES}; split the release"
        )
    return {
        "available": True,
        "base": "origin/main",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "content": completed.stdout,
    }


def _enrich_release_evidence(evidence: dict, *, include_review_diff: bool = False) -> dict:
    """Bind only release-relevant machine-readable evidence.

    Council Node compliance is deliberately restrictive and must not be injected
    into unrelated releases. Explicit changed release evidence and, during the
    canonical prepare path, the full bounded source diff are covered by the same
    evidence hash seen by all five independent reviewers.
    """
    enriched = dict(evidence)
    changed_files = [str(path) for path in evidence.get("changed_files", []) if isinstance(path, str)]
    if _council_node_release(changed_files) and COUNCIL_NODE_COMPLIANCE.is_file():
        enriched["law_governance_evidence"] = load(COUNCIL_NODE_COMPLIANCE)
    release_records = _release_specific_evidence(changed_files)
    if release_records:
        enriched["release_specific_evidence"] = release_records
    if include_review_diff:
        enriched["review_diff"] = _candidate_review_diff()
    return enriched


def prepare(args: argparse.Namespace) -> int:
    evidence = _enrich_release_evidence(load(args.evidence), include_review_diff=True)
    # Persist the exact evidence that will be sent to all Council reviewers. The
    # release request binds its canonical SHA-256 digest so a later evidence change
    # cannot inherit an earlier approval.
    dump(args.evidence, evidence)
    evidence_hash = sha256_json(evidence)

    scope = f"merge PR #{args.pr} to main only"
    approval = {
        "approval_id": f"github_pr_{args.pr}_founder_comment_{args.founder_comment_id}",
        "approver": "human_overseer",
        "approved": True,
        "scope": scope,
        "head_sha": args.head_sha,
        "authorization_sequence": 1,
        "source": {
            "provider": "github",
            "repository": args.repository,
            "pull_request": args.pr,
            "comment_id": int(args.founder_comment_id),
        },
    }
    approval["approval_hash"] = hash_without(approval, "approval_hash")

    checks = evidence.get("checks", [])
    failed = [
        item.get("name", "unknown")
        for item in checks
        if item.get("status") == "completed" and item.get("conclusion") not in {"success", "neutral", "skipped"}
    ]
    ready = not failed
    request = {
        "release_request_id": f"pr{args.pr}_{args.head_sha[:12]}_main_merge",
        "release_class": "main_branch_merge",
        "scope": scope,
        "head_sha": args.head_sha,
        "evidence_hash": evidence_hash,
        "evidence_hash_algorithm": "sha256_canonical_json",
        "technical_readiness": {
            "ready": ready,
            "failed_checks": failed,
            "evidence_source": "exact_head_github_check_runs_plus_bound_release_evidence_and_complete_diff",
        },
        "external_effects": False,
        "human_authorization_id": approval["approval_id"],
        "human_authorization_hash": approval["approval_hash"],
        "human_authorization_sequence": approval["authorization_sequence"],
    }
    request["release_request_hash"] = hash_without(request, "release_request_hash")

    dump(args.human_output, approval)
    dump(args.request_output, request)
    Path(args.hash_output).write_text(request["release_request_hash"] + "\n", encoding="utf-8")
    print(request["release_request_hash"])
    return 0 if ready else 2


def finalize(args: argparse.Namespace) -> int:
    request = load(args.request)
    human = load(args.human)
    evidence_hash = str(request.get("evidence_hash", ""))
    if len(evidence_hash) != 64 or any(c not in "0123456789abcdef" for c in evidence_hash.lower()):
        raise SystemExit("release request missing valid bound evidence hash")

    receipt_dir = Path(args.receipts)
    reviews: list[dict] = []
    for sequence, council_id in enumerate(ORDER, start=2):
        receipt = load(receipt_dir / f"{council_id}.json")
        if receipt.get("council_id") != council_id:
            raise SystemExit(f"council identity mismatch: {council_id}")
        if receipt.get("head_sha") != request.get("head_sha"):
            raise SystemExit(f"head SHA mismatch: {council_id}")
        if receipt.get("release_request_hash") != request.get("release_request_hash"):
            raise SystemExit(f"release hash mismatch: {council_id}")
        if receipt.get("independent") is not True or receipt.get("is_human") is not False:
            raise SystemExit(f"invalid agent independence marker: {council_id}")
        raw = dict(receipt)
        receipt_hash = raw.pop("receipt_hash", None)
        if receipt_hash != sha256_json(raw):
            raise SystemExit(f"receipt hash mismatch: {council_id}")
        decision = receipt.get("verdict")
        findings = receipt.get("findings", [])
        conditions = findings if decision == "APPROVE_WITH_CONDITIONS" else []
        review = {
            "council_id": council_id,
            "release_request_hash": request["release_request_hash"],
            "independent": True,
            "review_sequence": sequence,
            "decision": decision,
            "reason": receipt.get("reason", ""),
            "conditions": [str(v) for v in conditions if isinstance(v, (str, int, float))],
            "receipt_hash": receipt_hash,
            "provider": receipt.get("provider"),
            "model": receipt.get("model"),
            "trace_id": receipt.get("trace_id"),
        }
        review["review_hash"] = hash_without(review, "review_hash")
        reviews.append(review)

    final = evaluate_final_release(
        release_request=request,
        human_authorization=human,
        council_reviews=reviews,
        final_release_policy=load(ROOT / "governance/final_release_policy.json"),
        council_policy=load(ROOT / "governance/five_council_policy.json"),
        activation_gates=load(ROOT / "governance/runtime_activation_gates.json"),
    )
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dump(out / "release_request.json", request)
    dump(out / "human_authorization.json", human)
    for review in reviews:
        dump(out / "reviews" / f"{review['council_id']}.json", review)
    dump(out / "final_decision.json", final)
    print(json.dumps(final, sort_keys=True, separators=(",", ":")))
    return 0 if final.get("decision") == "FINAL_RELEASE_APPROVED" else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--founder-comment-id", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--human-output", required=True)
    p.add_argument("--request-output", required=True)
    p.add_argument("--hash-output", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--request", required=True)
    f.add_argument("--human", required=True)
    f.add_argument("--receipts", required=True)
    f.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    return prepare(args) if args.cmd == "prepare" else finalize(args)


if __name__ == "__main__":
    raise SystemExit(main())
