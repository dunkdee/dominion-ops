#!/usr/bin/env python3
"""Read-only verification for an already-applied Dominion registry closure."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def index(records: list[dict], key: str, label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ValueError(f"invalid or duplicate {label} {key}: {value!r}")
        result[value] = record
    return result


def matches(record: dict, expected: dict) -> bool:
    return all(record.get(key) == value for key, value in expected.items())


def verify(system_dir: Path, founder: Path, strategizer: Path) -> dict:
    if not system_dir.is_dir() or system_dir.is_symlink():
        raise ValueError(f"unsafe or missing system directory: {system_dir}")
    overlay_path = system_dir / "canonical_manifest_v3_overlay_full_build.json"
    receipt_path = system_dir / "full_build_registry_receipt.json"
    component_path = system_dir / "component_registry.json"
    division_path = system_dir / "division_registry.json"
    for path in (overlay_path, receipt_path, component_path, division_path, founder, strategizer):
        if not path.is_file():
            raise ValueError(f"required closure evidence missing: {path}")

    overlay = read_json(overlay_path)
    receipt = read_json(receipt_path)
    components = read_json(component_path)
    divisions = read_json(division_path)
    if overlay.get("schema_version") != "dominion_full_build_overlay_v1" or not overlay.get("approved_for_overlay"):
        raise ValueError("canonical overlay is not approved")
    if receipt.get("schema") != "dominion-full-build-registry-receipt-v1":
        raise ValueError("closure receipt schema mismatch")
    if receipt.get("result") != "PASS" or receipt.get("mode") != "execute":
        raise ValueError("closure receipt does not record a successful execution")
    if not isinstance(components, list) or not isinstance(divisions, list):
        raise ValueError("registry evidence must contain JSON arrays")

    expected_sources = overlay.get("source_files", {})
    for key, path in (("founder_decisions_144", founder), ("strategizer_manifest", strategizer)):
        expected = expected_sources.get(key, {}).get("sha256")
        if not expected or sha256_file(path) != expected:
            raise ValueError(f"canonical source evidence mismatch: {key}")

    component_hash = sha256_file(component_path)
    division_hash = sha256_file(division_path)
    overlay_hash = sha256_file(overlay_path)
    post_hashes = receipt.get("post_hashes", {})
    if component_hash != post_hashes.get("component_registry"):
        raise ValueError("component registry does not match closure receipt")
    if division_hash != post_hashes.get("division_registry"):
        raise ValueError("division registry does not match closure receipt")
    if overlay_hash != post_hashes.get("final_overlay"):
        raise ValueError("canonical overlay does not match closure receipt")

    registry = index(components, "rel_path", "component")
    for decision in overlay.get("decisions", []):
        path = decision.get("rel_path")
        if path not in registry or not matches(registry[path], decision.get("approved_values", {})):
            raise ValueError(f"decision is not fully applied: {path}")
    for addition in overlay.get("additions", []):
        path = addition.get("rel_path")
        if path not in registry or registry[path] != addition.get("approved_record"):
            raise ValueError(f"addition is not fully applied: {path}")

    if sum(record.get("component_class") == "UNKNOWN" for record in registry.values()) != 0:
        raise ValueError("UNKNOWN records remain")
    if len(components) != overlay.get("counts", {}).get("post_overlay_component_records"):
        raise ValueError("component count differs from canonical overlay")

    division_index = index(divisions, "division_id", "division")
    if sum(int(item.get("unknown_count", -1)) for item in divisions) != 0:
        raise ValueError("division UNKNOWN count is not zero")
    if sum(int(item.get("total_component_count", -1)) for item in divisions) != len(components):
        raise ValueError("division membership total differs from component count")
    for division_id, division in division_index.items():
        members = sorted(
            record["rel_path"] for record in components
            if record.get("registry_included", True) and record.get("primary_division") == division_id
        )
        if division.get("member_paths") != members:
            raise ValueError(f"division membership drift: {division_id}")
        if division.get("runtime_status_breakdown") != dict(sorted(Counter(
            str(record.get("runtime_status", "UNKNOWN")) for record in components
            if record.get("registry_included", True) and record.get("primary_division") == division_id
        ).items())):
            raise ValueError(f"division runtime breakdown drift: {division_id}")

    required_holds = {
        "tiktok_chrome_upload.py": "DISABLED",
        "agents/tiktok_agent.py": "DISABLED",
        "agents/tiktok_api_agent.py": "DISABLED",
        "agents/tiktok_legal_video.py": "DISABLED",
        "agents/markov_lumibot_strategy.py": "PAPER_ONLY",
        "agents/markov_paper_trade.py": "PAPER_ONLY",
    }
    for path, expected in required_holds.items():
        if registry.get(path, {}).get("runtime_status") != expected:
            raise ValueError(f"governance hold violated: {path}")
    for path, record in registry.items():
        if path.startswith("voltedge/") and record.get("runtime_status") != "EXPERIMENTAL":
            raise ValueError(f"VoltEdge quarantine violated: {path}")

    return {
        "schema": "dominion-existing-registry-closure-verification-v1",
        "result": "PASS",
        "mode": "verify_existing",
        "component_records": len(components),
        "unknown_records": 0,
        "receipt": str(receipt_path),
        "hashes": {
            "component_registry": component_hash,
            "division_registry": division_hash,
            "canonical_overlay": overlay_hash,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-dir", type=Path, required=True)
    parser.add_argument("--founder-decisions", type=Path, required=True)
    parser.add_argument("--strategizer-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.system_dir.resolve(), args.founder_decisions.resolve(), args.strategizer_manifest.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"EXISTING_REGISTRY_CLOSURE=PASS components={result['component_records']} unknown=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
