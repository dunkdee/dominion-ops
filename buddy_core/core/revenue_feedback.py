"""Revenue attribution feedback.

PURCHASE_SOURCE: orders table in dominion-db.
  Populated exclusively by Stripe checkout.session.completed webhook (Group C).
  Every row is a confirmed purchase. No leads. No clicks. No inferences.

REVENUE_SOURCE: orders.amount_cents column only.
  Sum of recorded purchase amounts. Never fabricated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_UNKNOWN = "UNKNOWN"

ORDERS_SQL = """
    SELECT product_id, product_name, amount_cents, currency,
           utm_source, utm_medium, utm_campaign, utm_content, created_at
    FROM orders
    WHERE amount_cents IS NOT NULL AND amount_cents > 0
    ORDER BY created_at DESC
    LIMIT 1000
"""


def fetch_orders(conn) -> list[dict]:
    """Query confirmed purchase records from the orders table only.

    Never reads leads_captured, stripe_events, email_leads, or any other table.
    Every returned row is a confirmed Stripe purchase.
    """
    cur = conn.cursor()
    cur.execute(ORDERS_SQL)
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    return [dict(zip(cols, row)) for row in rows]


def _tally(orders: list[dict], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for o in orders:
        val = str(o.get(field) or "").strip()
        if val:
            out[val] = out.get(val, 0) + 1
    return out


def compute_revenue_feedback(
    orders: list[dict] | None,
    retrieved_at: str | None = None,
) -> tuple[dict, list]:
    """Deterministic governed feedback from canonical purchase records.

    orders=None  -> DB unavailable -> all UNKNOWN (fail closed).
    orders=[]    -> DB available, zero purchases -> revenue=0, not fabricated.
    orders=[...] -> compute from confirmed purchase evidence only.
    """
    ts = retrieved_at or datetime.now(timezone.utc).isoformat()

    # -- DB unavailable: fail closed ---------------------------------------
    if orders is None:
        result: dict[str, Any] = {
            "RETRIEVED_AT":        ts,
            "PURCHASE_SOURCE":     "orders table — dominion-db",
            "REVENUE_SOURCE":      "orders.amount_cents",
            "db_available":        False,
            "purchase_count":      _UNKNOWN,
            "revenue_cents":       _UNKNOWN,
            "product_breakdown":   _UNKNOWN,
            "utm_breakdown":       _UNKNOWN,
            "WINNER":              _UNKNOWN,
            "LOSER":               _UNKNOWN,
            "NEXT_CONSTRAINT":     "DB unavailable — purchase evidence inaccessible",
            "NEXT_ALLOWED_ACTION": "system.status",
            "APPROVAL_REQUIRED":   "NO",
        }
        return result, [{"type": "revenue_feedback", "retrieved_at": ts,
                         "db_available": False}]

    # -- Confirmed purchase evidence ---------------------------------------
    purchase_count = len(orders)
    revenue_cents  = sum(int(o.get("amount_cents") or 0) for o in orders)

    utm_breakdown = {
        "utm_source":   _tally(orders, "utm_source"),
        "utm_medium":   _tally(orders, "utm_medium"),
        "utm_campaign": _tally(orders, "utm_campaign"),
        "utm_content":  _tally(orders, "utm_content"),
    }
    product_breakdown = _tally(orders, "product_id")

    # WINNER/LOSER: purchase-attributed only; >= 2 distinct sources required
    source_tally = utm_breakdown["utm_source"]
    if purchase_count == 0 or len(source_tally) < 2:
        winner = _UNKNOWN
        loser  = _UNKNOWN
    else:
        ranked = sorted(source_tally.items(), key=lambda x: (-x[1], x[0]))
        winner = ranked[0][0]
        loser  = ranked[-1][0]

    # Next action — within standing authority only
    if purchase_count == 0:
        next_constraint = "Zero confirmed purchases in orders table"
        next_action     = "revenue.prepare"
        approval        = "NO"
    elif winner == _UNKNOWN:
        next_constraint = (
            f"{purchase_count} confirmed purchase(s); "
            "insufficient source diversity for winner determination"
        )
        next_action = "artifact.stage"
        approval    = "NO"
    else:
        next_constraint = (
            f"Scale {winner}: {source_tally[winner]}/{purchase_count} "
            "purchase(s) attributed to top channel"
        )
        next_action = "external.publish"
        approval    = "YES"

    result = {
        "RETRIEVED_AT":        ts,
        "PURCHASE_SOURCE":     "orders table — dominion-db",
        "REVENUE_SOURCE":      "orders.amount_cents",
        "db_available":        True,
        "purchase_count":      purchase_count,
        "revenue_cents":       revenue_cents,
        "product_breakdown":   product_breakdown,
        "utm_breakdown":       utm_breakdown,
        "WINNER":              winner,
        "LOSER":               loser,
        "NEXT_CONSTRAINT":     next_constraint,
        "NEXT_ALLOWED_ACTION": next_action,
        "APPROVAL_REQUIRED":   approval,
    }
    evidence = [{
        "type":           "revenue_feedback",
        "retrieved_at":   ts,
        "db_available":   True,
        "purchase_count": purchase_count,
        "revenue_cents":  revenue_cents,
    }]
    return result, evidence
