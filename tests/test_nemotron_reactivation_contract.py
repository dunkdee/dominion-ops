from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "governance" / "system_integrity_agent.json"
SCOPE = ROOT / "governance" / "nemotron_reactivation_scope_20260910.json"
GATE = ROOT / "governance" / "nemotron_reactivation_gate_20260910.json"
EVIDENCE = ROOT / "governance" / "nemotron_release_evidence_20260910.json"
UNIT = ROOT / "deploy" / "systemd" / "dominion-nemotron.service"
WORKER = ROOT / "apps" / "nemotron-worker" / "nemotron_worker.py"
WORKFLOW = ROOT / ".github" / "workflows" / "activate-nemotron-governed.yml"
ACTIVATE = ROOT / "scripts" / "nemotron" / "activate_nemotron.sh"
ROLLBACK_TEST = ROOT / "tests" / "test_nemotron_rollback_fault_injection.py"
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
    assert "NEMOTRON_NUM_CTX=4096" in unit
    assert "NEMOTRON_MAX_CONCURRENCY=1" in unit


def test_worker_enforces_capacity_admission_control() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    assert 'MAX_CONCURRENCY = max(1, int(os.getenv("NEMOTRON_MAX_CONCURRENCY", "1")))' in worker
    assert 'NUM_CTX = max(1024, int(os.getenv("NEMOTRON_NUM_CTX", "4096")))' in worker
    assert "_GENERATION_SLOTS.acquire(blocking=False)" in worker
    assert '"type": "capacity_busy"' in worker
    assert '"num_ctx": NUM_CTX' in worker


def test_release_evidence_addresses_council_holds_without_false_certification() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["truth_boundary"]["external_inference_provider_api_required"] is False
    assert evidence["truth_boundary"]["public_ingress_authorized"] is False
    assert evidence["license_and_terms"]["governing_terms"] == "NVIDIA Open Model License Agreement"
    assert evidence["license_and_terms"]["contract_compliance_certification_claimed"] is False
    capacity = evidence["capacity_plan_for_nemotron_service"]
    assert capacity["admission_controls_in_candidate"]["max_concurrent_generations"] == 1
    assert capacity["admission_controls_in_candidate"]["context_tokens"] == 4096
    assert evidence["operational_rollback_test"]["test_path"] == "tests/test_nemotron_rollback_fault_injection.py"
    assert evidence["business_case"]["new_external_provider_api_cost_authorized"] == 0
    assert evidence["business_case"]["direct_revenue_claim"] is False
    assert ROLLBACK_TEST.is_file()


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
    assert "VM repo is deliberately not advanced here" in script
    assert 'git -C "$staging" checkout -q --detach FETCH_HEAD' in script
    script_lower = script.lower()
    assert "firewall-rules create" not in script_lower
    assert "gcloud compute firewall-rules create" not in script_lower
    assert "ollama pull" not in script_lower
    assert "kill -9" not in script_lower
    assert "pkill" not in script_lower
    assert "killall" not in script_lower
    assert 'git -c "$repo" merge' not in script_lower
    assert 'git -c "$repo" reset' not in script_lower


def test_activation_transactionally_converges_command_center_route() -> None:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    script = ACTIVATE.read_text(encoding="utf-8")
    allowed = set(scope["allowed"])
    assert "bounded command-center runtime configuration of the Nemotron loopback URL and model with backup and rollback" in allowed
    assert "bounded command-center container recreation solely to load the reviewed Nemotron route configuration" in allowed
    assert 'CC_ENV_FILE="${COMMAND_CENTER_ENV_FILE:-$HOME/.config/dominion/command-center.env}"' in script
    assert 'cp -a "$CC_ENV_FILE" "$backup/command-center.env"' in script
    assert 'install -m 600 "$backup/command-center.env" "$CC_ENV_FILE"' in script
    assert "'NEMOTRON_BASE_URL': 'http://127.0.0.1:11435'" in script
    assert "'NEMOTRON_MODEL': model" in script
    assert 'docker compose --env-file "$CC_ENV_FILE"' in script
    assert "NEMOTRON_COMMAND_CENTER_CONFIG=PASS" in script
    assert "command_center_env_sha256" in script


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
