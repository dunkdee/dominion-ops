from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "governance" / "system_integrity_agent.json"
SCOPE = ROOT / "governance" / "nemotron_reactivation_scope_20260910.json"
GATE = ROOT / "governance" / "nemotron_reactivation_gate_20260910.json"
UNIT = ROOT / "deploy" / "systemd" / "dominion-nemotron.service"
WORKFLOW = ROOT / ".github" / "workflows" / "activate-nemotron-governed.yml"
ACTIVATE = ROOT / "scripts" / "nemotron" / "activate_nemotron.sh"
WORK_ORDER = ROOT / "docs" / "NEMOTRON_REACTIVATION_WORK_ORDER_20260910.md"
WATCHDOG = ROOT / ".github" / "workflows" / "watchdog.yml"


def test_founder_scope_is_bounded_and_five_council_gated() -> None:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert scope["status"] == "FOUNDER_SCOPE_AUTHORIZED"
    assert scope["final_gate"] == "five_council"
    assert gate["fail_closed"] is True
    forbidden = set(scope["not_authorized"])
    assert "public ingress to tcp 11435" in forbidden
    assert "firewall opening" in forbidden
    assert "model download without separate provenance approval" in forbidden
    assert "oracle activation" in forbidden


def test_integrity_contract_monitors_nemotron_as_active() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert "dominion-nemotron.service" in contract["active_units"]
    assert "dominion-nemotron.service" not in contract["containment_holds"]
    assert 11435 not in contract["absent_listeners"]
    checks = {item["id"]: item for item in contract["http_checks"]}
    assert checks["nemotron"] == {
        "id": "nemotron",
        "url": "http://127.0.0.1:11435/health",
        "expected_status": 200,
    }
    assert "nemotron" in contract["intelligence_probe"]["accepted_sources"]


def test_unit_is_loopback_only_and_uses_governed_release_path() -> None:
    unit = UNIT.read_text(encoding="utf-8")
    assert "Environment=NEMOTRON_LISTEN_HOST=127.0.0.1" in unit
    assert "Environment=NEMOTRON_LISTEN_HOST=0.0.0.0" not in unit
    assert "Requires=ollama.service" in unit
    assert "/.dominion/nemotron/runtime/release/apps/nemotron-worker" in unit
    assert "NEMOTRON_MODEL=nemotron-3-nano:4b" in unit


def test_activation_lane_is_founder_gated_and_does_not_open_ingress() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = ACTIVATE.read_text(encoding="utf-8")
    assert "ACTIVATE NEMOTRON" in workflow
    assert "foundation-vm-production" in workflow
    assert "github.actor" in workflow
    assert "github.triggering_actor" in workflow
    assert "enable --now \"$SERVICE\"" in script
    assert "NEMOTRON_COMMAND_CENTER_ROUTE=PASS" in script
    assert "NEMOTRON_INTEGRITY=PASS" in script
    assert "NEMOTRON_ROLLBACK=BEGIN" in script
    assert "vm_repo_dirty" in script
    assert "reset --hard \"$prior_repo_sha\"" in script
    lowered = (workflow + "\n" + script).lower()
    assert "firewall-rules create" not in lowered
    assert "gcloud compute firewall-rules create" not in lowered
    assert "ollama pull" not in lowered
    assert "kill -9" not in lowered
    assert "pkill" not in lowered
    assert "killall" not in lowered


def test_activation_requires_exact_main_sha_and_validates_receipt() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'requested=$REQUESTED_SHA current_main=$current_main' in workflow
    assert 'checkout=$checkout_sha requested=$REQUESTED_SHA' in workflow
    assert "/home/*/.dominion/nemotron/receipts/*.json" in workflow
    assert "d['release_sha'] == sys.argv[2]" in workflow
    assert "d['command_center_source'] == 'nemotron'" in workflow
    assert "d['external_ingress_opened'] is False" in workflow


def test_runtime_observer_no_longer_treats_nemotron_as_contained() -> None:
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    assert "check_active dominion-nemotron.service" in watchdog
    assert "check_http nemotron 200 http://127.0.0.1:11435/health" in watchdog
    assert "check_held dominion-nemotron.service" not in watchdog
    assert "CONTAINMENT_HOLD=BROKEN port=11435" not in watchdog


def test_work_order_requires_end_to_end_evidence_and_rollback() -> None:
    text = WORK_ORDER.read_text(encoding="utf-8")
    assert "Command Center `/api/chat`" in text
    assert "integrity agent reaches PASS with zero defects" in text
    assert "Five Council final release approval" in text
    assert "Rollback" in text
