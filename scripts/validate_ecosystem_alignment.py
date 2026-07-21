#!/usr/bin/env python3
"""Validate the Dominion ecosystem vertical registry and its repository contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "verticals.json"
ALLOWED_PILLARS = {"cash_flow", "systems", "scale"}
ALLOWED_MODES = {
    "assisted",
    "record_only",
    "draft_only",
    "research_only",
    "paper",
    "observe_and_route",
    "review_and_veto",
    "production_support",
}


class AlignmentError(ValueError):
    """Raised when an ecosystem governance invariant is violated."""


def require(condition: bool, message: str) -> None:
    """Raise a readable validation error when *condition* is false."""
    if not condition:
        raise AlignmentError(message)


def load_registry() -> dict[str, Any]:
    """Load and decode the machine-readable vertical registry."""
    require(REGISTRY_PATH.is_file(), f"missing registry: {REGISTRY_PATH}")
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlignmentError(f"invalid JSON: {exc}") from exc
    require(isinstance(data, dict), "registry root must be an object")
    return data


def validate_dependency_graph(verticals: list[dict[str, Any]]) -> None:
    """Ensure dependencies exist and do not contain directed cycles."""
    by_id = {vertical["id"]: vertical for vertical in verticals}
    for vertical in verticals:
        for dependency in vertical["dependencies"]:
            require(
                dependency in by_id,
                f"{vertical['id']}: unknown dependency {dependency!r}",
            )
            require(
                dependency != vertical["id"],
                f"{vertical['id']}: cannot depend on itself",
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(vertical_id: str) -> None:
        if vertical_id in visited:
            return
        require(vertical_id not in visiting, f"dependency cycle at {vertical_id}")
        visiting.add(vertical_id)
        for dependency in by_id[vertical_id]["dependencies"]:
            visit(dependency)
        visiting.remove(vertical_id)
        visited.add(vertical_id)

    for vertical_id in by_id:
        visit(vertical_id)


def validate_required_paths(verticals: list[dict[str, Any]]) -> None:
    """Ensure every declared implementation contract exists in the repository."""
    for vertical in verticals:
        for relative_path in vertical["required_paths"]:
            path = ROOT / relative_path
            require(path.exists(), f"{vertical['id']}: missing required path {relative_path}")


def validate_registry(registry: dict[str, Any]) -> None:
    """Enforce governance, ordering, safety, and repository invariants."""
    require(registry.get("schema_version") == 1, "schema_version must be 1")
    require(registry.get("operating_order") == ["cash_flow", "systems", "scale"],
            "operating_order must be cash_flow -> systems -> scale")

    principles = registry.get("principles")
    require(isinstance(principles, dict), "principles must be an object")
    for required_true in (
        "human_final_authority",
        "revenue_before_expansion",
        "shared_infrastructure_separate_vertical_accountability",
        "no_unverified_live_execution",
        "paper_before_live_financial_execution",
        "zero_secret_material_in_repository",
    ):
        require(principles.get(required_true) is True, f"principle {required_true} must be true")

    verticals = registry.get("verticals")
    require(isinstance(verticals, list) and verticals, "verticals must be a non-empty list")

    required_fields = {
        "id",
        "pillar",
        "priority",
        "operator",
        "status",
        "mode",
        "duty",
        "required_paths",
        "dependencies",
        "human_approval_required",
        "exit_gate",
    }
    ids: set[str] = set()
    priorities: set[int] = set()

    for vertical in verticals:
        require(isinstance(vertical, dict), "each vertical must be an object")
        missing = required_fields - vertical.keys()
        require(not missing, f"vertical missing fields: {sorted(missing)}")
        vertical_id = vertical["id"]
        require(isinstance(vertical_id, str) and vertical_id, "vertical id must be non-empty")
        require(vertical_id not in ids, f"duplicate vertical id: {vertical_id}")
        ids.add(vertical_id)

        priority = vertical["priority"]
        require(isinstance(priority, int) and priority > 0,
                f"{vertical_id}: priority must be a positive integer")
        require(priority not in priorities, f"duplicate priority: {priority}")
        priorities.add(priority)

        require(vertical["pillar"] in ALLOWED_PILLARS,
                f"{vertical_id}: invalid pillar {vertical['pillar']!r}")
        require(vertical["mode"] in ALLOWED_MODES,
                f"{vertical_id}: invalid mode {vertical['mode']!r}")
        require(isinstance(vertical["required_paths"], list) and vertical["required_paths"],
                f"{vertical_id}: required_paths must be non-empty")
        require(isinstance(vertical["dependencies"], list),
                f"{vertical_id}: dependencies must be a list")
        require(
            isinstance(vertical["human_approval_required"], list)
            and vertical["human_approval_required"],
            f"{vertical_id}: human approval gates must be non-empty",
        )
        require(isinstance(vertical["exit_gate"], str) and vertical["exit_gate"].strip(),
                f"{vertical_id}: exit_gate must be non-empty")

    require(priorities == set(range(1, len(verticals) + 1)),
            "vertical priorities must be contiguous starting at 1")
    ordered_ids = [item["id"] for item in sorted(verticals, key=lambda item: item["priority"])]
    require(ordered_ids[0] == "digital_products", "first vertical must be digital_products")
    require("infrastructure" in ids, "infrastructure vertical is required")
    require("governance_legal" in ids, "governance_legal vertical is required")
    require("intelligence_orchestration" in ids,
            "intelligence_orchestration vertical is required")

    trading = next(item for item in verticals if item["id"] == "trading")
    require(trading["mode"] == "paper", "trading must remain in paper mode")
    require(trading["status"] == "paper_only", "trading status must remain paper_only")
    require("enable_live_trading" in trading["human_approval_required"],
            "trading must require explicit approval before live execution")

    validate_dependency_graph(verticals)
    validate_required_paths(verticals)


def main() -> int:
    """Run validation and return a shell-friendly exit status."""
    try:
        registry = load_registry()
        validate_registry(registry)
    except AlignmentError as exc:
        print(f"ECOSYSTEM ALIGNMENT: FAIL — {exc}", file=sys.stderr)
        return 1

    verticals = registry["verticals"]
    print(f"ECOSYSTEM ALIGNMENT: PASS — {len(verticals)} verticals validated")
    for vertical in sorted(verticals, key=lambda item: item["priority"]):
        print(
            f"{vertical['priority']:02d} {vertical['id']} "
            f"[{vertical['pillar']}/{vertical['status']}/{vertical['mode']}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
