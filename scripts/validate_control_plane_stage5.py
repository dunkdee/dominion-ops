#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from control_plane.analytics_audit import build_growth_intelligence_audit
from control_plane.external_estimates import adapt_external_estimate

ERRORS: list[str] = []
REQUIRED = [
    ROOT / "control_plane/external_estimates.py",
    ROOT / "control_plane/analytics_audit.py",
    ROOT / "governance/data_monetization_policy.json",
    ROOT / "governance/schemas/external_estimate_snapshot.schema.json",
    ROOT / "governance/schemas/external_estimate_result.schema.json",
    ROOT / "governance/schemas/growth_intelligence_report.schema.json",
    ROOT / "revenue_products/storefront_growth_intelligence.json",
    ROOT / "runtime/examples/stage5_external_estimate_fixture.json",
    ROOT / "scripts/stage5_market_intelligence.py",
    ROOT / "tests/test_control_plane_stage5.py",
    ROOT / "architecture/STAGE5_MARKET_INTELLIGENCE.md",
]

def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)

def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        ERRORS.append(f"cannot load {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(value, dict), f"{path.relative_to(ROOT)} must contain an object")
    return value if isinstance(value, dict) else {}

def main() -> int:
    for path in REQUIRED:
        require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")
    gates = load(ROOT / "governance/runtime_activation_gates.json")
    require(gates.get("stage") == 5, "activation stage must be 5")
    require(gates.get("mode") == "shadow_only", "mode must remain shadow_only")
    require(gates.get("external_execution_enabled") is False, "external execution must remain disabled")
    blocked = set(gates.get("blocked_capabilities", []))
    require("estimated_data_revenue_verification" in blocked, "estimated data may not verify revenue")
    require("raw_personal_data_commercialization" in blocked, "raw personal data commercialization must be blocked")
    policy = load(ROOT / "governance/data_monetization_policy.json")
    require(policy.get("default_behavior") == "deny", "data monetization policy must default deny")
    require("sell_raw_personal_data" in policy.get("prohibited_practices", []), "raw personal data sale must be prohibited")
    fixture = load(ROOT / "runtime/examples/stage5_external_estimate_fixture.json")
    signal = adapt_external_estimate(fixture)
    require(signal.get("status") == "ESTIMATED_MARKET_SIGNAL", "fixture must adapt as an estimated signal")
    require(signal.get("revenue_verified") is False, "estimate may not verify revenue")
    audit = build_growth_intelligence_audit(signal)
    require(audit.get("status") == "MARKET_SIGNAL_ONLY", "fixture audit must remain market-signal-only")
    require(audit.get("external_execution_authorized") is False, "audit may not authorize execution")
    require(audit.get("pricing_status") == "UNSET_REQUIRES_HUMAN_APPROVAL", "pricing must remain human-gated")
    for name in ("external_estimate_snapshot.schema.json","external_estimate_result.schema.json","growth_intelligence_report.schema.json"):
        schema = load(ROOT / "governance/schemas" / name)
        require(schema.get("additionalProperties") is False, f"{name} must reject unknown fields")
    if ERRORS:
        print("Dominion Stage 5 validation FAILED:")
        for error in ERRORS:
            print(f" - {error}")
        return 1
    print("Dominion Stage 5 validation PASSED")
    print(f"Validated {len(REQUIRED)} Stage 5 contracts and components.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
