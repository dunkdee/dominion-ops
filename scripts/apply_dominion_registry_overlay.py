#!/usr/bin/env python3
"""Validate and atomically apply a governed Dominion registry overlay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_index(records: list[dict], key: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ValueError(f"invalid or duplicate {key}: {value!r}")
        result[value] = record
    return result


def exact_match(record: dict, expected: dict) -> bool:
    return all(record.get(key) == value for key, value in expected.items())


def recalculate_divisions(components: list[dict], divisions: list[dict], generated_at: str) -> list[dict]:
    division_by_id = unique_index(copy.deepcopy(divisions), "division_id")
    included = [record for record in components if record.get("registry_included", True)]
    unknown_divisions = sorted({record.get("primary_division") for record in included} - set(division_by_id))
    if unknown_divisions:
        raise ValueError(f"components reference missing divisions: {unknown_divisions}")

    for division_id, division in division_by_id.items():
        members = sorted(
            (record for record in included if record.get("primary_division") == division_id),
            key=lambda record: record["rel_path"],
        )
        py_members = [record for record in members if str(record["rel_path"]).endswith(".py")]
        external_members = [record for record in members if not str(record["rel_path"]).endswith(".py")]
        division["py_candidate_count"] = len(py_members)
        division["external_component_count"] = len(external_members)
        division["total_component_count"] = len(members)
        division["unknown_count"] = sum(record.get("component_class") == "UNKNOWN" for record in members)
        division["manual_review_required_count"] = sum(bool(record.get("manual_review_required")) for record in members)
        division["member_paths"] = [record["rel_path"] for record in members]
        division["runtime_status_breakdown"] = dict(sorted(Counter(
            str(record.get("runtime_status", "UNKNOWN")) for record in members
        ).items()))
        division["role_evidence_level_breakdown"] = dict(sorted(Counter(
            str(record.get("role_evidence_level", "UNKNOWN")) for record in members
        ).items()))
        division["generated_at"] = generated_at
        division["generated_from"] = "dominion_full_build_overlay_v1"
    return [division_by_id[key] for key in sorted(division_by_id)]


def stage_file(directory: Path, filename: str, content: bytes) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=directory)
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def source_path_for(
    system_dir: Path,
    source_key: str,
    source: dict,
    founder_decisions: Path,
    strategizer_manifest: Path,
) -> Path:
    if source_key == "founder_decisions_144":
        return founder_decisions
    if source_key == "strategizer_manifest":
        return strategizer_manifest
    return system_dir / source["filename"]


def apply(args: argparse.Namespace) -> dict:
    system_dir = args.system_dir.resolve()
    if not system_dir.is_dir() or system_dir.is_symlink():
        raise ValueError(f"unsafe or missing system directory: {system_dir}")
    overlay_path = args.overlay.resolve()
    founder_decisions = args.founder_decisions.resolve()
    strategizer_manifest = args.strategizer_manifest.resolve()
    overlay = read_json(overlay_path)
    if overlay.get("schema_version") != "dominion_full_build_overlay_v1" or not overlay.get("approved_for_overlay"):
        raise ValueError("overlay is not an approved Dominion full-build overlay")
    if not overlay.get("application_requirements", {}).get("validate_all_old_values"):
        raise ValueError("overlay does not require old-value validation")

    source_results = {}
    for key, expected in overlay.get("source_files", {}).items():
        path = source_path_for(system_dir, key, expected, founder_decisions, strategizer_manifest)
        if not path.is_file():
            raise ValueError(f"overlay source missing: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected.get("sha256"):
            raise ValueError(f"overlay source hash mismatch: {path.name}")
        source_results[key] = {"path": str(path), "sha256": actual_hash}

    component_path = system_dir / "component_registry.json"
    division_path = system_dir / "division_registry.json"
    components = read_json(component_path)
    divisions = read_json(division_path)
    if not isinstance(components, list) or not isinstance(divisions, list):
        raise ValueError("registry inputs must be JSON arrays")
    registry = unique_index(copy.deepcopy(components), "rel_path")

    applied = 0
    already_applied = 0
    for decision in overlay.get("decisions", []):
        path = decision.get("rel_path")
        if path not in registry:
            raise ValueError(f"decision path missing from registry: {path}")
        record = registry[path]
        old_values = decision.get("old_values", {})
        approved_values = decision.get("approved_values", {})
        old_match = exact_match(record, old_values)
        approved_match = exact_match(record, approved_values)
        if old_match:
            record.update(copy.deepcopy(approved_values))
            applied += 1
        elif approved_match:
            already_applied += 1
        else:
            raise ValueError(f"mixed or drifted decision state: {path}")

    additions_applied = 0
    additions_already_applied = 0
    for addition in overlay.get("additions", []):
        path = addition.get("rel_path")
        approved_record = addition.get("approved_record", {})
        if not addition.get("expected_absent") or approved_record.get("rel_path") != path:
            raise ValueError(f"invalid overlay addition: {path}")
        if path not in registry:
            registry[path] = copy.deepcopy(approved_record)
            additions_applied += 1
        elif registry[path] == approved_record:
            additions_already_applied += 1
        else:
            raise ValueError(f"drifted overlay addition state: {path}")

    original_paths = [record["rel_path"] for record in components]
    addition_paths = sorted(path for path in registry if path not in set(original_paths))
    ordered_components = [registry[path] for path in original_paths + addition_paths]
    pre_unknown = sum(record.get("component_class") == "UNKNOWN" for record in components)
    post_unknown = sum(record.get("component_class") == "UNKNOWN" for record in ordered_components)
    if post_unknown != overlay.get("counts", {}).get("post_overlay_unknown") or post_unknown != 0:
        raise ValueError(f"post-application UNKNOWN invariant failed: {post_unknown}")
    expected_post_components = overlay.get("counts", {}).get("post_overlay_component_records")
    if len(ordered_components) != expected_post_components:
        raise ValueError(f"post-overlay component count mismatch: {len(ordered_components)} != {expected_post_components}")

    expected_holds = overlay.get("protected_holds", {})
    if expected_holds.get("tiktok") != "DISABLED" or expected_holds.get("markov") != "PAPER_ONLY":
        raise ValueError("overlay governance holds are incomplete")
    for path in ("tiktok_chrome_upload.py", "agents/tiktok_agent.py", "agents/tiktok_api_agent.py", "agents/tiktok_legal_video.py"):
        if registry[path].get("runtime_status") != "DISABLED":
            raise ValueError(f"TikTok hold violated: {path}")
    for path in ("agents/markov_lumibot_strategy.py", "agents/markov_paper_trade.py"):
        if registry[path].get("runtime_status") != "PAPER_ONLY":
            raise ValueError(f"paper-only hold violated: {path}")
    for path, record in registry.items():
        if path.startswith("voltedge/") and record.get("runtime_status") != "EXPERIMENTAL":
            raise ValueError(f"VoltEdge quarantine violated: {path}")

    generated_at = datetime.now(timezone.utc).isoformat()
    updated_divisions = recalculate_divisions(ordered_components, divisions, generated_at)
    if sum(item["total_component_count"] for item in updated_divisions) != len(ordered_components):
        raise ValueError("division membership total does not equal component count")
    if sum(item["py_candidate_count"] for item in updated_divisions) != len(components):
        raise ValueError("Python candidate total changed unexpectedly")
    if sum(item["external_component_count"] for item in updated_divisions) != additions_applied + additions_already_applied:
        raise ValueError("external component total does not match overlay additions")
    if sum(item["unknown_count"] for item in updated_divisions) != 0:
        raise ValueError("division registry retains UNKNOWN records")

    component_bytes = json_bytes(ordered_components)
    division_bytes = json_bytes(updated_divisions)
    overlay_bytes = json_bytes(overlay)
    receipt = {
        "schema": "dominion-full-build-registry-receipt-v1",
        "generated_at": generated_at,
        "mode": "execute" if args.execute else "dry_run",
        "result": "PASS",
        "system_dir": str(system_dir),
        "counts": {
            "component_records": len(ordered_components),
            "decisions": len(overlay.get("decisions", [])),
            "applied": applied,
            "already_applied": already_applied,
            "additions_applied": additions_applied,
            "additions_already_applied": additions_already_applied,
            "pre_unknown": pre_unknown,
            "post_unknown": post_unknown,
        },
        "source_validation": source_results,
        "pre_hashes": {
            "component_registry": sha256_file(component_path),
            "division_registry": sha256_file(division_path),
        },
        "post_hashes": {
            "component_registry": sha256_bytes(component_bytes),
            "division_registry": sha256_bytes(division_bytes),
            "final_overlay": sha256_bytes(overlay_bytes),
        },
        "protected_holds": expected_holds,
        "backup_dir": None,
        "rollback_performed": False,
    }

    if not args.execute:
        return receipt
    if already_applied or additions_already_applied:
        raise ValueError("execute mode requires a clean pre-application state; already-applied decisions found")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = system_dir / "backups" / f"full-build-registry-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    receipt["backup_dir"] = str(backup_dir)
    targets = {
        component_path: component_bytes,
        division_path: division_bytes,
        system_dir / "canonical_manifest_v3_overlay_full_build.json": overlay_bytes,
        system_dir / "full_build_registry_receipt.json": b"",
    }
    original_state: dict[Path, Path | None] = {}
    staged: dict[Path, Path] = {}
    for target in targets:
        if target.exists():
            backup = backup_dir / target.name
            shutil.copy2(target, backup)
            original_state[target] = backup
        else:
            original_state[target] = None

    receipt_bytes = json_bytes(receipt)
    targets[system_dir / "full_build_registry_receipt.json"] = receipt_bytes
    try:
        for target, content in targets.items():
            staged[target] = stage_file(system_dir, target.name, content)
        for target, temp_path in staged.items():
            os.replace(temp_path, target)
        staged.clear()
        if sha256_file(component_path) != receipt["post_hashes"]["component_registry"]:
            raise ValueError("post-write component registry hash mismatch")
        if sha256_file(division_path) != receipt["post_hashes"]["division_registry"]:
            raise ValueError("post-write division registry hash mismatch")
    except Exception:
        receipt["rollback_performed"] = True
        for target, backup in original_state.items():
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                shutil.copy2(backup, target)
        raise
    finally:
        for temp_path in staged.values():
            temp_path.unlink(missing_ok=True)

    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-dir", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--founder-decisions", type=Path, required=True)
    parser.add_argument("--strategizer-manifest", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--receipt-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = apply(args)
    rendered = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if args.receipt_output:
        args.receipt_output.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_output.write_text(rendered, encoding="utf-8")
    print(
        "REGISTRY_OVERLAY=PASS "
        f"mode={receipt['mode']} decisions={receipt['counts']['decisions']} "
        f"applied={receipt['counts']['applied']} pre_unknown={receipt['counts']['pre_unknown']} "
        f"post_unknown={receipt['counts']['post_unknown']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
