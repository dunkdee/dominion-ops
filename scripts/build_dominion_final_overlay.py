#!/usr/bin/env python3
"""Build the final Dominion registry overlay from exact governed inputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


MUTABLE_FIELDS = (
    "component_class",
    "primary_division",
    "runtime_status",
    "classification_source",
    "assignment_basis",
    "manual_review_required",
    "classification_notes",
)

VOLTEDGE_PATHS = {
    "voltedge/ve_constants.py",
    "voltedge/ve_content_engine.py",
    "voltedge/ve_orchestrator.py",
    "voltedge/ve_product_catalog.py",
    "voltedge/ve_seo_blog_engine.py",
    "voltedge/ve_shopping_feed.py",
    "voltedge/ve_social_distributor.py",
}

HOLD_STATUSES = {
    "tiktok_chrome_upload.py": "DISABLED",
    "agents/tiktok_agent.py": "DISABLED",
    "agents/tiktok_api_agent.py": "DISABLED",
    "agents/tiktok_legal_video.py": "DISABLED",
    "agents/markov_lumibot_strategy.py": "PAPER_ONLY",
    "agents/markov_paper_trade.py": "PAPER_ONLY",
    "upwork_login.py": "RETIRED",
    "agents/upwork_agent.py": "RETIRED",
    "agents/upwork_submitter.py": "RETIRED",
    "agents/pph_agent.py": "RETIRED",
    "agents/pph_navigator.py": "RETIRED",
    "agents/pph_submitter.py": "RETIRED",
    "agents/freelance_agent.py": "RETIRED",
    "agents/freelancer_submitter.py": "RETIRED",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_index(records: list[dict], key: str, label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} record missing {key}")
        if value in result:
            raise ValueError(f"duplicate {label} {key}: {value}")
        result[value] = record
    return result


def record_matches(record: dict, expected: dict) -> bool:
    return all(record.get(key) == value for key, value in expected.items())


def apply_decision(registry_by_path: dict[str, dict], decision: dict) -> None:
    path = decision["rel_path"]
    if path not in registry_by_path:
        raise ValueError(f"overlay path missing from registry: {path}")
    record = registry_by_path[path]
    old_values = decision["old_values"]
    approved_values = decision["approved_values"]
    if not record_matches(record, old_values):
        raise ValueError(f"old-value mismatch while modeling overlay: {path}")
    record.update(copy.deepcopy(approved_values))


def build_overlay(args: argparse.Namespace) -> dict:
    source_paths = {
        "component_registry": args.component_registry,
        "division_registry": args.division_registry,
        "phase5b_overlay": args.phase5b_overlay,
        "phase4e_queue": args.phase4e_queue,
        "phase4e_evidence": args.phase4e_evidence,
        "founder_decisions_144": args.founder_decisions,
        "strategizer_manifest": args.strategizer_manifest,
    }
    registry = read_json(args.component_registry)
    division_registry = read_json(args.division_registry)
    phase5b = read_json(args.phase5b_overlay)
    queue = read_json(args.phase4e_queue)
    evidence = read_json(args.phase4e_evidence)
    founder_doc = read_json(args.founder_decisions)
    strategizer_manifest = read_json(args.strategizer_manifest)

    if not isinstance(registry, list) or not isinstance(division_registry, list):
        raise ValueError("component and division registries must be JSON arrays")
    if not isinstance(queue, list) or not isinstance(evidence, list):
        raise ValueError("Phase 4E queue and evidence must be JSON arrays")
    if len(queue) != 133 or len(evidence) != 133:
        raise ValueError(f"expected 133 Phase 4E records, found queue={len(queue)} evidence={len(evidence)}")
    if phase5b.get("schema_version") != "phase5b_overlay_v1" or not phase5b.get("approved_for_overlay"):
        raise ValueError("existing Phase 5B overlay is not the approved v1 overlay")
    if strategizer_manifest.get("schema") != "dominion-provenance-repair-145-deployed-source-v1":
        raise ValueError("Strategizer deployed-source manifest schema mismatch")
    if strategizer_manifest.get("service") != "dominion-strategizer":
        raise ValueError("Strategizer service identity mismatch")
    if strategizer_manifest.get("secret_scan", {}).get("status") != "PASS":
        raise ValueError("Strategizer source secret scan is not PASS")

    registry_by_path = unique_index(copy.deepcopy(registry), "rel_path", "component")
    queue_by_path = unique_index(queue, "rel_path", "queue")
    evidence_by_path = unique_index(evidence, "rel_path", "evidence")
    founder_by_path = unique_index(founder_doc.get("decisions", []), "rel_path", "Founder decision")
    if len(founder_by_path) != 31:
        raise ValueError(f"expected 31 Founder decisions from issue 144, found {len(founder_by_path)}")
    if set(queue_by_path) != set(evidence_by_path):
        raise ValueError("Phase 4E queue/evidence path sets differ")

    pre_unknown = sum(record.get("component_class") == "UNKNOWN" for record in registry_by_path.values())
    if pre_unknown != 133:
        raise ValueError(f"expected pre-application UNKNOWN count 133, found {pre_unknown}")

    decisions: list[dict] = []
    phase5b_paths: set[str] = set()
    for original in phase5b.get("decisions", []):
        decision = copy.deepcopy(original)
        path = decision.get("rel_path")
        if not path or path in phase5b_paths:
            raise ValueError(f"invalid or duplicate Phase 5B path: {path}")
        phase5b_paths.add(path)
        decision["governed_source"] = "approved_phase5b_overlay"
        apply_decision(registry_by_path, decision)
        decisions.append(decision)

    unresolved_queue = {
        path for path, decision in queue_by_path.items()
        if decision.get("component_class") == "UNKNOWN"
    }
    if unresolved_queue != set(founder_by_path):
        missing = sorted(unresolved_queue - set(founder_by_path))
        extra = sorted(set(founder_by_path) - unresolved_queue)
        raise ValueError(f"issue 144 decision paths do not match the 31 UNKNOWN proposals; missing={missing} extra={extra}")

    for path in sorted(queue_by_path):
        if path in phase5b_paths:
            continue
        queue_decision = queue_by_path[path]
        record = registry_by_path.get(path)
        if record is None:
            raise ValueError(f"Phase 4E queue path missing from registry: {path}")

        if queue_decision.get("component_class") == "UNKNOWN":
            approved = founder_by_path[path]
            governed_source = "founder_approved_issue_144"
        else:
            approved = queue_decision
            governed_source = "phase4e_evidence_queue_full_build_approval"

        approved_class = approved["component_class"]
        approved_division = approved["primary_division"]
        approved_status = approved["runtime_status"]
        if path in VOLTEDGE_PATHS:
            approved_division = "M"
            approved_status = "EXPERIMENTAL"

        old_values = {field: copy.deepcopy(record.get(field)) for field in MUTABLE_FIELDS}
        new_values = {
            "component_class": approved_class,
            "primary_division": approved_division,
            "runtime_status": approved_status,
            "classification_source": "REVIEWED_CLASSIFICATION",
            "assignment_basis": f"CLASS:{approved_class}",
            "manual_review_required": False,
            "classification_notes": (
                f"Applied by governed full-build overlay; source={governed_source}; "
                f"evidence={queue_decision.get('reference_evidence_type', 'reviewed_source')}."
            ),
        }
        decision = {
            "rel_path": path,
            "decision_type": "PHASE4E_FINAL_CLASSIFICATION",
            "approved_for_overlay": True,
            "old_values": old_values,
            "approved_values": new_values,
            "fields_changed": [field for field in MUTABLE_FIELDS if old_values.get(field) != new_values.get(field)],
            "governed_source": governed_source,
            "queue_proposal": {
                "component_class": queue_decision.get("component_class"),
                "primary_division": queue_decision.get("primary_division"),
                "runtime_status": queue_decision.get("runtime_status"),
                "division_confidence": queue_decision.get("division_confidence"),
                "classification_basis": queue_decision.get("classification_basis"),
            },
        }
        apply_decision(registry_by_path, decision)
        decisions.append(decision)

    post_unknown = sum(record.get("component_class") == "UNKNOWN" for record in registry_by_path.values())
    if post_unknown != 0:
        remaining = sorted(path for path, record in registry_by_path.items() if record.get("component_class") == "UNKNOWN")
        raise ValueError(f"final overlay leaves UNKNOWN records: {remaining}")

    for path, expected_status in HOLD_STATUSES.items():
        record = registry_by_path.get(path)
        if not record:
            raise ValueError(f"governance hold path missing: {path}")
        if record.get("runtime_status") != expected_status:
            raise ValueError(f"governance hold violated for {path}: {record.get('runtime_status')} != {expected_status}")
    for path in VOLTEDGE_PATHS:
        record = registry_by_path.get(path)
        if not record or record.get("runtime_status") != "EXPERIMENTAL" or record.get("primary_division") != "M":
            raise ValueError(f"VoltEdge quarantine violated for {path}")

    strategizer_path = "apps/strategizer"
    if strategizer_path in registry_by_path:
        raise ValueError("Strategizer registry addition is not absent")
    strategizer_record = {
        "rel_path": strategizer_path,
        "filename": "strategizer",
        "directory": "apps",
        "candidate_kind": "EXTERNAL_SERVICE",
        "size_bytes": strategizer_manifest["source_archive_bytes"],
        "mtime_iso": strategizer_manifest["generated_at_utc"],
        "is_nested_agents": False,
        "sha256": strategizer_manifest["source_archive_sha256"],
        "evidence": {
            "service": strategizer_manifest["service"],
            "project": strategizer_manifest["project"],
            "region": strategizer_manifest["region"],
            "latest_ready_revision": strategizer_manifest["latest_ready_revision"],
            "image_digest": strategizer_manifest["image_digest"],
            "source_files": strategizer_manifest["files"],
            "secret_scan": strategizer_manifest["secret_scan"],
        },
        "parse_status": "EXTERNAL_VERIFIED",
        "identical_hash_paths": [],
        "evidence_note": "Exact Cloud Run build-source archive recovered, secret-scanned, versioned, and mapped to the ready revision under provenance repair #145.",
        "identity_status": "CONFIRMED",
        "canonical_id": "dominion_strategizer_cloud_run",
        "is_representation_of": None,
        "identity_confidence": "HIGH",
        "identity_note": "Immutable source archive, Cloud Build, image digest, and ready revision are mapped in runtime/records/provenance_repair_145.",
        "component_class": "API_SERVICE",
        "runtime_status": "DEPLOYED_DOCUMENTED",
        "role_evidence_level": "SOURCE_VERIFIED",
        "operational_evidence_level": "DEPLOYED_DOCUMENTED",
        "classification_source": "REVIEWED_CLASSIFICATION",
        "classification_notes": "Registered through the Founder-authorized full-build overlay after provenance repair #145.",
        "division_hint": "C",
        "primary_division": "C",
        "assignment_basis": "CLASS:API_SERVICE",
        "registry_included": True,
        "manual_review_required": False,
        "generated_from": "dominion_full_build_overlay_v1",
    }

    return {
        "schema_version": "dominion_full_build_overlay_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "scripts/build_dominion_final_overlay.py",
        "approved_for_overlay": True,
        "authorization": {
            "phase5b_overlay": "approved_for_overlay=true",
            "phase4e_issue": "https://github.com/dunkdee/dominion-ops/issues/144",
            "phase4e_approval": founder_doc.get("approval_record"),
            "full_build": "Founder selected full ecosystem build option 3 on 2026-08-11",
        },
        "source_files": {
            name: {"filename": path.name, "sha256": file_sha256(path)}
            for name, path in source_paths.items()
        },
        "counts": {
            "component_records": len(registry),
            "post_overlay_component_records": len(registry) + 1,
            "pre_overlay_unknown": pre_unknown,
            "post_overlay_unknown": post_unknown,
            "existing_phase5b_decisions": len(phase5b.get("decisions", [])),
            "phase4e_queue_records": len(queue),
            "issue_144_founder_decisions": len(founder_by_path),
            "total_overlay_decisions": len(decisions),
        },
        "protected_holds": {
            "tiktok": "DISABLED",
            "markov": "PAPER_ONLY",
            "dominion_alpha": "PAPER_ONLY",
            "nemotron": "FROZEN",
            "retired_workstreams": "RETIRED",
            "voltedge_laptop_modules": "EXPERIMENTAL_QUARANTINE",
            "payments": "NOT_AUTHORIZED",
            "live_trading": "NOT_AUTHORIZED",
        },
        "application_requirements": {
            "validate_all_old_values": True,
            "atomic_files": ["component_registry.json", "division_registry.json"],
            "backup_required": True,
            "rollback_on_failure": True,
            "receipt_required": True,
        },
        "additions": [
            {
                "rel_path": strategizer_path,
                "expected_absent": True,
                "approved_record": strategizer_record,
                "governed_source": "founder_approved_provenance_repair_145_and_full_build_option_3",
            }
        ],
        "decisions": decisions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-registry", type=Path, required=True)
    parser.add_argument("--division-registry", type=Path, required=True)
    parser.add_argument("--phase5b-overlay", type=Path, required=True)
    parser.add_argument("--phase4e-queue", type=Path, required=True)
    parser.add_argument("--phase4e-evidence", type=Path, required=True)
    parser.add_argument("--founder-decisions", type=Path, required=True)
    parser.add_argument("--strategizer-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    overlay = build_overlay(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "FINAL_OVERLAY_BUILD=PASS "
        f"decisions={overlay['counts']['total_overlay_decisions']} "
        f"pre_unknown={overlay['counts']['pre_overlay_unknown']} "
        f"post_unknown={overlay['counts']['post_overlay_unknown']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
