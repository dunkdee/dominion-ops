import json
from pathlib import Path


POLICY = Path("governance/commercial_closure_gate_v1.json")


def load_policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_commercial_ready_requires_all_core_gates():
    policy = load_policy()
    assert policy["governance"] == "RADAH MEMSHALAH"
    assert policy["states"] == ["VERIFIED_PASS", "BLOCKED", "RETIRED"]
    required = set(policy["required_gates"])
    assert {
        "infrastructure",
        "security",
        "backup_restore",
        "buddy_execution",
        "storefront",
        "payments",
        "order_receipt",
        "refund_receipt",
        "attribution",
        "traffic",
        "observability",
        "customer_policies",
        "revenue_receipt",
        "rollback_recovery",
    } <= required


def test_commercial_closure_forbids_false_completion_and_parallel_authority():
    anti = load_policy()["anti_drift"]
    for key in (
        "new_orchestrator_while_canonical_work_open",
        "parallel_memory_authority",
        "parallel_analytics_authority",
        "self_report_counts_as_completion",
        "silent_failure_allowed",
        "open_dependency_can_be_done",
        "production_change_without_rollback",
        "production_change_without_runtime_verification",
    ):
        assert anti[key] is False


def test_commercial_closure_sequence_is_forward_only():
    assert load_policy()["closure_sequence"] == [
        "inventory_truth",
        "infrastructure_repair",
        "buddy_production_readiness",
        "first_verified_revenue_loop",
        "controlled_scale",
    ]


def test_mistakes_reopen_the_gate_until_retested():
    assert load_policy()["mistake_protocol"] == [
        "acknowledge",
        "isolate",
        "correct",
        "retest",
        "record_evidence",
        "reopen_gate_until_pass",
    ]
