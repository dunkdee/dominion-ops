#!/usr/bin/env python3
"""Run/verify Five Council agent receipts without sharing deliberation.

Provider execution is external to this script. Each seat receives only the common
release evidence plus its own mandate; prior seat outputs are never included.
"""
from __future__ import annotations

import argparse, hashlib, json, pathlib, sys
from datetime import datetime, timezone

SEATS = {
    "truth_evidence": ["source_quality","factual_support","contradictions","uncertainty","hallucination_risk"],
    "law_governance": ["jurisdiction","legal_authority","contracts","privacy","regulation","internal_authority"],
    "security_risk": ["least_privilege","attack_surface","data_exposure","fraud","blast_radius","reversibility"],
    "engineering_reliability": ["architecture","tests","dependencies","observability","capacity","rollback"],
    "business_human_impact": ["revenue_relevance","cost","customer_outcome","ethics","reputation","strategic_alignment"],
}
ALLOWED = {"APPROVE","APPROVE_WITH_CONDITIONS","HOLD","VETO"}

def canon(v): return json.dumps(v, sort_keys=True, separators=(",",":"), ensure_ascii=False)
def sha(v): return hashlib.sha256(canon(v).encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

def prompt(seat, head_sha, release_hash, evidence):
    if seat not in SEATS: raise SystemExit(f"unknown seat: {seat}")
    evidence_hash = sha(evidence)
    return (
        "You are one independent Dominion Five Council reviewer. Do not assume any other council verdict. "
        "Review only your mandate and the supplied evidence. Fail closed on missing or contradictory evidence. "
        "Return JSON only with keys verdict, reason, findings, evidence_refs. verdict must be one of "
        "APPROVE, APPROVE_WITH_CONDITIONS, HOLD, VETO.\n"
        f"seat={seat}\nmandate={json.dumps(SEATS[seat])}\nhead_sha={head_sha}\nrelease_request_hash={release_hash}\n"
        f"evidence_hash={evidence_hash}\nevidence={canon(evidence)}"
    )

def _decode_content(content):
    if isinstance(content, dict): return content
    if not isinstance(content, str): raise SystemExit("provider returned no JSON council content")
    text=content.strip()
    if text.startswith("```"):
        text=text.strip("`").strip()
        if text.lower().startswith("json"): text=text[4:].strip()
    return json.loads(text)

def extract_provider_response(raw):
    obj=json.loads(raw)
    if not isinstance(obj, dict): raise SystemExit("provider returned non-object JSON")
    if "verdict" in obj: return obj
    if isinstance(obj.get("response"), str): return _decode_content(obj["response"])
    message=obj.get("message")
    if isinstance(message, dict) and message.get("content") is not None:
        return _decode_content(message.get("content"))
    choices=obj.get("choices")
    if isinstance(choices, list) and choices:
        choice=choices[0] if isinstance(choices[0], dict) else {}
        msg=choice.get("message") if isinstance(choice, dict) else None
        if isinstance(msg, dict) and msg.get("content") is not None:
            return _decode_content(msg.get("content"))
    raise SystemExit("unsupported provider response shape")

def make_receipt(args):
    response=extract_provider_response(pathlib.Path(args.response).read_text())
    verdict=response.get("verdict")
    if verdict not in ALLOWED: raise SystemExit("invalid council verdict")
    body={
        "schema":"dominion-five-council-agent-receipt-v1",
        "council_id":args.seat,
        "head_sha":args.head_sha,
        "release_request_hash":args.release_hash,
        "independent":True,
        "is_human":False,
        "provider":args.provider,
        "model":args.model,
        "trace_id":args.trace_id,
        "prompt_hash":args.prompt_hash,
        "verdict":verdict,
        "reason":str(response.get("reason", "")).strip(),
        "findings":response.get("findings", []),
        "evidence_refs":response.get("evidence_refs", []),
        "observed_at":now(),
    }
    body["receipt_hash"]=sha(body)
    pathlib.Path(args.output).write_text(json.dumps(body, indent=2, sort_keys=True)+"\n")

def verify(args):
    receipts=[json.loads(p.read_text()) for p in sorted(pathlib.Path(args.dir).glob("*.json"))]
    by={r.get("council_id"):r for r in receipts}
    errors=[]
    if set(by)!=set(SEATS): errors.append("missing_or_unknown_council_receipts")
    if len(receipts)!=len(by): errors.append("duplicate_council_identity")
    for seat,r in by.items():
        rh=r.get("receipt_hash"); tmp=dict(r); tmp.pop("receipt_hash",None)
        if rh!=sha(tmp): errors.append(f"{seat}:receipt_hash_mismatch")
        if r.get("head_sha")!=args.head_sha: errors.append(f"{seat}:head_sha_mismatch")
        if r.get("release_request_hash")!=args.release_hash: errors.append(f"{seat}:release_hash_mismatch")
        if r.get("independent") is not True: errors.append(f"{seat}:not_independent")
        if r.get("is_human") is not False: errors.append(f"{seat}:agent_receipt_marked_human")
        if r.get("verdict") not in ALLOWED: errors.append(f"{seat}:invalid_verdict")
    blockers=[f"{s}:{by[s]['verdict']}" for s in SEATS if s in by and by[s]["verdict"] in {"HOLD","VETO"}]
    decision={
        "schema":"dominion-five-council-agent-decision-v1",
        "head_sha":args.head_sha,
        "release_request_hash":args.release_hash,
        "approvals":[s for s in SEATS if s in by and by[s]["verdict"] in {"APPROVE","APPROVE_WITH_CONDITIONS"}],
        "blockers":blockers,
        "errors":errors,
        "decision":"FINAL_RELEASE_APPROVED" if not errors and not blockers and len(by)==5 else "HOLD",
        "final_affirmative_gate":"five_council",
        "observed_at":now(),
    }
    decision["decision_hash"]=sha(decision)
    pathlib.Path(args.output).write_text(json.dumps(decision, indent=2, sort_keys=True)+"\n")
    print(canon(decision))
    return 0 if decision["decision"]=="FINAL_RELEASE_APPROVED" else 2

def _verify_bound_evidence(evidence: dict) -> None:
    """Fail if prompt evidence diverges from the already-canonical release request."""
    request_path = pathlib.Path("release_request.json")
    if not request_path.is_file():
        return
    request = json.loads(request_path.read_text())
    expected = request.get("evidence_hash")
    if not expected:
        raise SystemExit("release request missing bound evidence hash")
    actual = sha(evidence)
    if actual != expected:
        raise SystemExit(f"review evidence hash mismatch: expected={expected} actual={actual}")

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd", required=True)
    p=sp.add_parser("prompt"); p.add_argument("--seat",required=True); p.add_argument("--head-sha",required=True); p.add_argument("--release-hash",required=True); p.add_argument("--evidence",required=True); p.add_argument("--output",required=True)
    r=sp.add_parser("receipt"); r.add_argument("--seat",required=True); r.add_argument("--head-sha",required=True); r.add_argument("--release-hash",required=True); r.add_argument("--response",required=True); r.add_argument("--provider",default="governed-local"); r.add_argument("--model",default="runtime-resolved"); r.add_argument("--trace-id",required=True); r.add_argument("--prompt-hash",required=True); r.add_argument("--output",required=True)
    v=sp.add_parser("verify"); v.add_argument("--dir",required=True); v.add_argument("--head-sha",required=True); v.add_argument("--release-hash",required=True); v.add_argument("--output",required=True)
    a=ap.parse_args()
    if a.cmd=="prompt":
        evidence=json.loads(pathlib.Path(a.evidence).read_text()); _verify_bound_evidence(evidence); text=prompt(a.seat,a.head_sha,a.release_hash,evidence); pathlib.Path(a.output).write_text(text); print(hashlib.sha256(text.encode()).hexdigest()); return 0
    if a.cmd=="receipt": make_receipt(a); return 0
    if a.cmd=="verify": return verify(a)
    return 2

if __name__=="__main__": sys.exit(main())
