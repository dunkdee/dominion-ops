#!/usr/bin/env bash
set -Eeuo pipefail

: "${EXPERIMENT_ID:?EXPERIMENT_ID is required}"
: "${ORDER_ID:?ORDER_ID is required}"
: "${PURCHASE_FLOW_ID:?PURCHASE_FLOW_ID is required}"
: "${CHECKOUT_ID:?CHECKOUT_ID is required}"
: "${PRODUCT_ID:?PRODUCT_ID is required}"

api="http://127.0.0.1:8790"
state_root="$HOME/.dominion/revenue-runtime"
runtime_root="$state_root/runtime"
db_path="$state_root/revenue.db"
env_file="$HOME/dominion-ops/.env"
operator_token=""

[[ "$EXPERIMENT_ID" =~ ^[A-Za-z0-9_-]{3,120}$ ]] || { echo 'GATE_E_LIVE_RECONCILE=HOLD reason=invalid_experiment_id'; exit 20; }
[[ "$ORDER_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo 'GATE_E_LIVE_RECONCILE=HOLD reason=invalid_order_id'; exit 21; }
[[ "$PURCHASE_FLOW_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo 'GATE_E_LIVE_RECONCILE=HOLD reason=invalid_purchase_flow_id'; exit 22; }
[[ "$CHECKOUT_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo 'GATE_E_LIVE_RECONCILE=HOLD reason=invalid_checkout_id'; exit 23; }

systemctl is-active --quiet dominion-revenue-runtime.service
systemctl is-active --quiet dominion-revenue-evaluator.timer
test -s "$db_path"
test -d "$runtime_root"
test -s "$env_file"

health="$(mktemp)"
trap 'rm -f "$health"' EXIT
curl -fsS "$api/health" > "$health"
python3 - "$health" <<'PY'
import json, sys
obj = json.load(open(sys.argv[1], encoding="utf-8"))
assert obj.get("status") == "ok", obj
assert obj.get("execution_enabled") is False, obj
assert obj.get("automatic_price_changes") is False, obj
assert obj.get("automatic_paid_spend") is False, obj
print("GATE_E_LIVE_RUNTIME_HEALTH=PASS execution_enabled=false price_automation=false paid_spend=false")
PY

# Reconcile the already-completed Wix order through the canonical evaluator.
sudo systemctl reset-failed dominion-revenue-evaluator.service >/dev/null 2>&1 || true
sudo systemctl start dominion-revenue-evaluator.service
test "$(sudo systemctl show dominion-revenue-evaluator.service -p Result --value)" = "success"
echo "GATE_E_LIVE_EVALUATOR_RUN=PASS"

buddy_exec="$(systemctl show dominion-buddy-web.service -p ExecStart --value 2>/dev/null || true)"
buddy_python="$(printf '%s\n' "$buddy_exec" | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
test -n "$buddy_python"
test -x "$buddy_python"

# Load the same Wix credentials used by the canonical systemd runtime.
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
test -n "${WIX_API_KEY:-}"
test -n "${WIX_SITE_ID:-}"

PYTHONPATH="$runtime_root" "$buddy_python" - "$db_path" "$EXPERIMENT_ID" "$ORDER_ID" "$PURCHASE_FLOW_ID" "$CHECKOUT_ID" "$PRODUCT_ID" <<'PY'
import json
import sqlite3
import sys

from apps.revenue_runtime import wix_adapter
from apps.revenue_runtime.evaluator import load_policy
from apps.revenue_runtime.store import RevenueStore

db_path, exp_id, order_id, purchase_flow_id, checkout_id, product_id = sys.argv[1:]
db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

# Independently re-read the exact paid Wix order through the same canonical adapter.
orders = wix_adapter.search_recent_paid_orders(limit=100)
matches = [o for o in orders if str(o.get("id") or "") == order_id]
assert len(matches) == 1, f"authorized Wix order not found exactly once: {order_id}"
order = matches[0]
assert str(order.get("purchase_flow_id") or "") == purchase_flow_id, order
assert str(order.get("checkout_id") or "") == checkout_id, order
items = [i for i in order.get("items", []) if i.get("product_id") == product_id]
assert items, order
assert sum(int(i.get("revenue_cents") or 0) for i in items) == 0, items
print(
    f"GATE_E_WIX_ORDER_PROOF=PASS order_id={order_id} product_id={product_id} "
    f"purchase_flow_id={purchase_flow_id} checkout_id={checkout_id} paid=true revenue_cents=0"
)

exp = db.execute(
    """SELECT id,product_id,status,treatment_pct,auto_promote
       FROM experiments WHERE id=?""",
    (exp_id,),
).fetchone()
assert exp is not None, f"experiment missing: {exp_id}"
assert exp["product_id"] == product_id, dict(exp)
assert exp["status"] == "active", dict(exp)
assert int(exp["treatment_pct"]) == 0, dict(exp)
assert int(exp["auto_promote"]) == 0, dict(exp)
print(
    f"GATE_E_LIVE_EXPERIMENT_PROOF=PASS experiment_id={exp_id} "
    f"product_id={product_id} status=active treatment_pct=0 auto_promote=false"
)

rec = db.execute(
    """SELECT order_id,experiment_id,status,reason,visitor_id,revenue_cents,reconciled_at
       FROM order_reconciliation WHERE order_id=? AND experiment_id=?""",
    (order_id, exp_id),
).fetchone()
assert rec is not None, f"order reconciliation missing for {order_id}"
assert rec["status"] == "attributed", dict(rec)
assert rec["visitor_id"], dict(rec)
assert int(rec["revenue_cents"]) == 0, dict(rec)
visitor_id = str(rec["visitor_id"])

links = db.execute(
    """SELECT link_type,link_id,visitor_id,variant,linked_at
       FROM attribution_bridge_links
       WHERE experiment_id=?
         AND ((link_type='purchase_flow' AND link_id=?)
              OR (link_type='checkout' AND link_id=?))
       ORDER BY linked_at ASC""",
    (exp_id, purchase_flow_id, checkout_id),
).fetchall()

variant = "control"
if rec["reason"] in {"WIX_PURCHASE_FLOW_LINK", "WIX_CHECKOUT_LINK"}:
    assert links, "native reconciliation reason has no matching bridge link"
    identities = {(str(row["visitor_id"]), str(row["variant"])) for row in links}
    assert len(identities) == 1, [dict(row) for row in links]
    native_visitor, native_variant = next(iter(identities))
    assert native_visitor == visitor_id, (native_visitor, visitor_id)
    assert native_variant == variant, native_variant
    link_types = sorted({row["link_type"] for row in links})
    print(
        f"GATE_E_WIX_NATIVE_LINK=PASS experiment_id={exp_id} order_id={order_id} "
        f"link_types={','.join(link_types)} variant={variant}"
    )
elif rec["reason"] == "UNIQUE_PRODUCT_CLICK_WINDOW":
    # Preserve the canonical fallback exactly as implemented: one and only one signed
    # click candidate in the governed lookback window, joined to the exact live Wix order.
    store = RevenueStore(db_path)
    policy = load_policy()
    lookback = int(policy["attribution"]["order_attribution_lookback_minutes"])
    candidates = store.click_candidates(exp_id, str(order.get("created_date") or ""), lookback)
    assert len(candidates) == 1, candidates
    candidate = candidates[0]
    assert str(candidate["visitor_id"]) == visitor_id, (candidate, visitor_id)
    assert str(candidate["variant"]) == variant, candidate
    print(
        f"GATE_E_WIX_ORDER_IDENTITY_JOIN=PASS experiment_id={exp_id} order_id={order_id} "
        f"purchase_flow_id={purchase_flow_id} checkout_id={checkout_id} "
        f"visitor_id={visitor_id} variant={variant} reason=UNIQUE_PRODUCT_CLICK_WINDOW "
        "candidate_count=1"
    )
else:
    raise AssertionError(f"unsupported attribution reason: {rec['reason']}")

print(
    f"SOURCE_TO_ORDER_ATTRIBUTION_RECEIPT=PASS order_id={order_id} "
    f"experiment_id={exp_id} visitor_id={visitor_id} variant={variant} "
    f"revenue_cents=0 reason={rec['reason']}"
)

events = db.execute(
    """SELECT id,visitor_id,variant,event_type,revenue_cents,metadata_json
       FROM events WHERE experiment_id=? ORDER BY occurred_at ASC""",
    (exp_id,),
).fetchall()
counts = {}
order_purchases = []
for row in events:
    counts[row["event_type"]] = counts.get(row["event_type"], 0) + 1
    if row["event_type"] != "purchase":
        continue
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    if str(meta.get("order_id") or "") == order_id:
        order_purchases.append(row)

assert counts.get("impression", 0) >= 1, counts
assert counts.get("click", 0) >= 1, counts
assert len(order_purchases) == 1, f"expected one idempotent purchase event, got {len(order_purchases)}"
purchase = order_purchases[0]
assert str(purchase["visitor_id"]) == visitor_id, dict(purchase)
assert str(purchase["variant"]) == variant, dict(purchase)
assert int(purchase["revenue_cents"]) == 0, dict(purchase)
print(
    f"GATE_E_EVENT_LEDGER_PROOF=PASS experiment_id={exp_id} order_id={order_id} "
    f"impression_events={counts.get('impression',0)} click_events={counts.get('click',0)} "
    "purchase_events=1 purchase_revenue_cents=0 idempotent=true"
)

db.close()
PY

operator_token="$(python3 - "$env_file" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
if not p.is_file():
    raise SystemExit(2)
for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() != "WIX_AGENT_OPERATOR_TOKEN":
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    print(value)
    break
PY
)"
test -n "$operator_token"

# Pause only after the complete attribution proof passes.
curl -fsS -X POST -H "X-Operator-Token: $operator_token" \
  "$api/control/experiments/$EXPERIMENT_ID/pause" >/dev/null

python3 - "$db_path" "$EXPERIMENT_ID" <<'PY'
import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
row = db.execute("SELECT status FROM experiments WHERE id=?", (sys.argv[2],)).fetchone()
assert row and row[0] == "paused", row
db.close()
print(f"GATE_E_LIVE_CANARY_PAUSED=PASS experiment_id={sys.argv[2]} final_state=paused")
PY

echo "GATE_E_LIVE_RECONCILE=PASS experiment_id=$EXPERIMENT_ID order_id=$ORDER_ID product_id=$PRODUCT_ID spend_cents=0 new_payment=false new_refund=false"
