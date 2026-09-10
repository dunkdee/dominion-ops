import hashlib, importlib.util, json, pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("five", ROOT / "scripts" / "run_five_council_agents.py")
five = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(five)


def _receipt(seat, head="abc", release="rel", verdict="APPROVE"):
    body = {
        "schema":"dominion-five-council-agent-receipt-v1",
        "council_id":seat,
        "head_sha":head,
        "release_request_hash":release,
        "independent":True,
        "is_human":False,
        "provider":"test",
        "model":"test",
        "trace_id":f"trace-{seat}",
        "prompt_hash":"p",
        "verdict":verdict,
        "reason":"ok",
        "findings":[],
        "evidence_refs":[],
        "observed_at":"2026-09-09T00:00:00+00:00",
    }
    body["receipt_hash"] = five.sha(body)
    return body


def test_prompt_is_seat_scoped():
    evidence={"checks":["green"]}
    p=five.prompt("security_risk","abc","rel",evidence)
    assert "security_risk" in p
    assert "least_privilege" in p
    assert "truth_evidence" not in p
    assert f"evidence_hash={five.sha(evidence)}" in p


def test_bound_evidence_passes(tmp_path, monkeypatch):
    evidence={"checks":["green"],"law_governance_evidence":{"release_scope":"code_only_predeployment"}}
    (tmp_path/"release_request.json").write_text(json.dumps({"evidence_hash":five.sha(evidence)}))
    monkeypatch.chdir(tmp_path)
    five._verify_bound_evidence(evidence)


def test_bound_evidence_mismatch_fails_closed(tmp_path, monkeypatch):
    evidence={"checks":["green"]}
    (tmp_path/"release_request.json").write_text(json.dumps({"evidence_hash":"0"*64}))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="review evidence hash mismatch"):
        five._verify_bound_evidence(evidence)


def test_verify_all_five_approves(tmp_path):
    for seat in five.SEATS:
        (tmp_path/f"{seat}.json").write_text(json.dumps(_receipt(seat)))
    class A: pass
    a=A(); a.dir=str(tmp_path); a.head_sha="abc"; a.release_hash="rel"; a.output=str(tmp_path/"decision.json")
    assert five.verify(a)==0
    d=json.loads(pathlib.Path(a.output).read_text())
    assert d["decision"]=="FINAL_RELEASE_APPROVED"
    assert len(d["approvals"])==5


def test_verify_hold_blocks(tmp_path):
    for seat in five.SEATS:
        verdict="HOLD" if seat=="security_risk" else "APPROVE"
        (tmp_path/f"{seat}.json").write_text(json.dumps(_receipt(seat, verdict=verdict)))
    class A: pass
    a=A(); a.dir=str(tmp_path); a.head_sha="abc"; a.release_hash="rel"; a.output=str(tmp_path/"decision.json")
    assert five.verify(a)==2
    d=json.loads(pathlib.Path(a.output).read_text())
    assert d["decision"]=="HOLD"


def test_verify_hash_mismatch_blocks(tmp_path):
    for seat in five.SEATS:
        r=_receipt(seat)
        if seat=="truth_evidence": r["reason"]="tampered"
        (tmp_path/f"{seat}.json").write_text(json.dumps(r))
    class A: pass
    a=A(); a.dir=str(tmp_path); a.head_sha="abc"; a.release_hash="rel"; a.output=str(tmp_path/"decision.json")
    assert five.verify(a)==2
    d=json.loads(pathlib.Path(a.output).read_text())
    assert any("receipt_hash_mismatch" in e for e in d["errors"])
