from __future__ import annotations

import argparse
import json

from scripts import canonicalize_five_council_release as release


def test_unrelated_release_does_not_inherit_council_node_compliance() -> None:
    evidence = {
        "changed_files": ["apps/nemotron-worker/nemotron_worker.py"],
        "checks": [],
        "nemotron_release_evidence": {"runtime": "local_loopback"},
    }
    enriched = release._enrich_release_evidence(evidence)
    assert "law_governance_evidence" not in enriched
    assert enriched["nemotron_release_evidence"] == {"runtime": "local_loopback"}


def test_council_node_release_keeps_its_compliance_evidence() -> None:
    evidence = {"changed_files": ["apps/council_node/app/main.py"], "checks": []}
    enriched = release._enrich_release_evidence(evidence)
    assert enriched["law_governance_evidence"] == release.load(release.COUNCIL_NODE_COMPLIANCE)


def test_prepare_binds_actual_pr_number_into_scope(tmp_path) -> None:
    evidence = tmp_path / "evidence.json"
    human = tmp_path / "human.json"
    request = tmp_path / "request.json"
    release_hash = tmp_path / "release_hash.txt"
    evidence.write_text(json.dumps({"changed_files": ["docs/example.md"], "checks": []}))
    args = argparse.Namespace(
        pr=777,
        repository="dunkdee/dominion-ops",
        head_sha="a" * 40,
        founder_comment_id="12345",
        evidence=str(evidence),
        human_output=str(human),
        request_output=str(request),
        hash_output=str(release_hash),
    )

    assert release.prepare(args) == 0
    human_doc = json.loads(human.read_text())
    request_doc = json.loads(request.read_text())
    assert human_doc["scope"] == "merge PR #777 to main only"
    assert request_doc["scope"] == "merge PR #777 to main only"
    assert "#279" not in human_doc["scope"]
