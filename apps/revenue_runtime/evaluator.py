from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .attribution_bridge import AttributionBridgeStore
from .core import deterministic_variant, evaluate_treatment
from .store import RevenueStore
from . import wix_adapter


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "governance" / "revenue_execution_policy.json"


def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def runtime_enabled(policy: dict[str, Any]) -> bool:
    switch = policy["kill_switch"]
    return os.getenv(switch["environment_variable"], "0") == switch["enabled_value"]


def _native_order_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(uuid.UUID(text))
    except ValueError:
        return ""


def reconcile_paid_orders(store: RevenueStore, policy: dict[str, Any]) -> list[dict[str, Any]]:
    lookback = int(policy["attribution"]["order_attribution_lookback_minutes"])
    receipts: list[dict[str, Any]] = []
    active = store.list_experiments("active")
    if not active:
        return receipts

    bridge = AttributionBridgeStore(store.path)
    orders = wix_adapter.search_recent_paid_orders(limit=100)
    for exp in active:
        for order in orders:
            order_id = str(order.get("id") or "")
            created = str(order.get("created_date") or "")
            if not order_id or not created:
                continue
            prior = [
                item for item in store.attributed_reconciliations_for_order(order_id)
                if item.get("experiment_id") == exp["id"]
            ]
            if prior:
                continue
            relevant = [item for item in order.get("items", []) if item.get("product_id") == exp["product_id"]]
            if not relevant:
                continue
            revenue_cents = sum(int(item.get("revenue_cents") or 0) for item in relevant)

            native_links = bridge.order_links(
                experiment_id=exp["id"],
                purchase_flow_id=str(order.get("purchase_flow_id") or ""),
                checkout_id=str(order.get("checkout_id") or ""),
                order_id=_native_order_id(order_id),
            )
            native_identities = {
                (str(item["visitor_id"]), str(item["variant"]))
                for item in native_links
            }
            if len(native_identities) > 1:
                reason = "CONFLICTING_WIX_NATIVE_LINKS"
                store.record_reconciliation(
                    order_id=order_id,
                    exp_id=exp["id"],
                    status="unattributed",
                    reason=reason,
                    revenue_cents=revenue_cents,
                )
                receipts.append({
                    "order_id": order_id,
                    "experiment_id": exp["id"],
                    "status": "unattributed",
                    "reason": reason,
                })
                continue

            if len(native_identities) == 1:
                visitor_id, variant = next(iter(native_identities))
                expected = deterministic_variant(exp["id"], visitor_id, int(exp["treatment_pct"]))
                if variant != expected:
                    reason = "WIX_NATIVE_VARIANT_MISMATCH"
                    store.record_reconciliation(
                        order_id=order_id,
                        exp_id=exp["id"],
                        status="unattributed",
                        reason=reason,
                        revenue_cents=revenue_cents,
                    )
                    receipts.append({
                        "order_id": order_id,
                        "experiment_id": exp["id"],
                        "status": "unattributed",
                        "reason": reason,
                    })
                    continue
                if any(item["link_type"] == "purchase_flow" for item in native_links):
                    reason = "WIX_PURCHASE_FLOW_LINK"
                elif any(item["link_type"] == "checkout" for item in native_links):
                    reason = "WIX_CHECKOUT_LINK"
                else:
                    reason = "WIX_ORDER_LINK"
            else:
                candidates = store.click_candidates(exp["id"], created, lookback)
                if len(candidates) != 1:
                    reason = "NO_CANDIDATE" if not candidates else "AMBIGUOUS_CANDIDATES"
                    store.record_reconciliation(
                        order_id=order_id,
                        exp_id=exp["id"],
                        status="unattributed",
                        reason=reason,
                        revenue_cents=revenue_cents,
                    )
                    receipts.append({
                        "order_id": order_id,
                        "experiment_id": exp["id"],
                        "status": "unattributed",
                        "reason": reason,
                    })
                    continue
                candidate = candidates[0]
                visitor_id = candidate["visitor_id"]
                variant = candidate["variant"]
                reason = "UNIQUE_PRODUCT_CLICK_WINDOW"

            event_id = f"wix-order:{order_id}:{exp['id']}"
            inserted = store.record_event(
                event_id=event_id,
                experiment_id=exp["id"],
                visitor_id=visitor_id,
                variant=variant,
                event_type="purchase",
                revenue_cents=revenue_cents,
                metadata={
                    "source": "wix_paid_order",
                    "order_id": order_id,
                    "attribution_reason": reason,
                },
                occurred_at=created,
            )
            store.record_reconciliation(
                order_id=order_id,
                exp_id=exp["id"],
                status="attributed",
                reason=reason,
                visitor_id=visitor_id,
                revenue_cents=revenue_cents,
            )
            receipts.append({
                "order_id": order_id,
                "experiment_id": exp["id"],
                "status": "attributed",
                "reason": reason,
                "variant": variant,
                "revenue_cents": revenue_cents,
                "event_inserted": inserted,
                "receipt": "SOURCE_TO_ORDER_ATTRIBUTION_RECEIPT=PASS",
            })
    return receipts


def reconcile_refunds(store: RevenueStore) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for order in wix_adapter.search_recent_refunded_orders(limit=100):
        order_id = str(order.get("id") or "")
        if not order_id:
            continue
        reconciliations = store.attributed_reconciliations_for_order(order_id)
        if not reconciliations:
            continue
        refunds = wix_adapter.get_succeeded_refunds(order_id)
        for link in reconciliations:
            exp_id = str(link["experiment_id"])
            visitor_id = str(link.get("visitor_id") or "")
            if not visitor_id:
                continue
            exp = store.get_experiment(exp_id)
            variant = deterministic_variant(exp_id, visitor_id, int(exp["treatment_pct"]))
            for refund in refunds:
                refund_id = str(refund["refund_id"])
                payment_id = str(refund["payment_id"])
                refund_cents = int(refund["refund_cents"])
                event_id = f"wix-refund:{refund_id}:{payment_id}:{exp_id}"
                inserted = store.record_event(
                    event_id=event_id,
                    experiment_id=exp_id,
                    visitor_id=visitor_id,
                    variant=variant,
                    event_type="refund",
                    revenue_cents=refund_cents,
                    metadata={
                        "source": "wix_refund",
                        "order_id": order_id,
                        "refund_id": refund_id,
                        "payment_id": payment_id,
                        "external_refund": bool(refund.get("external_refund", False)),
                    },
                    occurred_at=str(refund.get("created_date") or "") or None,
                )
                if not inserted:
                    continue
                receipts.append({
                    "order_id": order_id,
                    "experiment_id": exp_id,
                    "refund_id": refund_id,
                    "status": "refund_attributed",
                    "variant": variant,
                    "refund_cents": refund_cents,
                    "receipt": "ORDER_REFUND_ATTRIBUTION_RECEIPT=PASS",
                })
    return receipts


def evaluate_one(store: RevenueStore, exp_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    exp = store.get_experiment(exp_id)
    metrics = store.metrics(exp_id)
    evaluation = evaluate_treatment(metrics, policy).as_dict()
    receipt: dict[str, Any] = {
        "experiment_id": exp_id,
        "metrics": metrics,
        "evaluation": evaluation,
        "promotion": None,
    }
    if evaluation["decision"] != "PROMOTE_TREATMENT":
        return receipt
    if not exp["auto_promote"]:
        store.mark_decision(exp_id, "winner_ready", "treatment")
        receipt["promotion"] = {"status": "HELD", "reason": "AUTO_PROMOTE_DISABLED"}
        return receipt
    required_event = policy["attribution"]["auto_promotion_requires_success_event"]
    if exp["success_event"] != required_event:
        store.mark_decision(exp_id, "winner_ready", "treatment")
        receipt["promotion"] = {"status": "HELD", "reason": "PURCHASE_EVIDENCE_REQUIRED"}
        return receipt
    if not runtime_enabled(policy):
        receipt["promotion"] = {"status": "HELD", "reason": "KILL_SWITCH_DISABLED"}
        return receipt
    allowed = set(policy["wix"]["allowed_product_fields"])
    if exp["wix_field"] not in allowed or exp["wix_field"] != "plainDescription":
        receipt["promotion"] = {"status": "HELD", "reason": "FIELD_NOT_ALLOWLISTED"}
        return receipt
    after_value = str(exp["treatment"].get("wix_value") or "")
    if not after_value:
        receipt["promotion"] = {"status": "HELD", "reason": "TREATMENT_WIX_VALUE_MISSING"}
        return receipt
    mutation = wix_adapter.update_plain_description(exp["product_id"], after_value)
    promotion = store.record_promotion(
        experiment_id=exp_id,
        product_id=exp["product_id"],
        field=mutation["field"],
        before_value=mutation["before_value"],
        after_value=mutation["after_value"],
        before_revision=mutation["before_revision"],
        after_revision=mutation["after_revision"],
    )
    receipt["promotion"] = {"status": "PROMOTED", "receipt": promotion}
    return receipt


def run_cycle(db_path: str | Path) -> dict[str, Any]:
    policy = load_policy()
    store = RevenueStore(db_path)
    reconciled = reconcile_paid_orders(store, policy)
    refunds_reconciled = reconcile_refunds(store)
    evaluated = [evaluate_one(store, exp["id"], policy) for exp in store.list_experiments("active")]
    return {
        "reconciled": reconciled,
        "refunds_reconciled": refunds_reconciled,
        "evaluated": evaluated,
    }


def main() -> int:
    db_path = os.getenv("DOMINION_REVENUE_DB", str(Path.home() / ".dominion/revenue-runtime/revenue.db"))
    try:
        receipt = run_cycle(db_path)
    except Exception as exc:
        print(json.dumps({"DOMINION_REVENUE_CYCLE": "FAIL", "error": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    for item in receipt["reconciled"]:
        if item.get("status") == "attributed":
            print(
                "SOURCE_TO_ORDER_ATTRIBUTION_RECEIPT=PASS "
                f"order_id={item['order_id']} experiment_id={item['experiment_id']} "
                f"variant={item['variant']} revenue_cents={item['revenue_cents']}"
            )
    for item in receipt["refunds_reconciled"]:
        print(
            "ORDER_REFUND_ATTRIBUTION_RECEIPT=PASS "
            f"order_id={item['order_id']} experiment_id={item['experiment_id']} "
            f"refund_id={item['refund_id']} refund_cents={item['refund_cents']}"
        )
    print("DOMINION_REVENUE_CYCLE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
