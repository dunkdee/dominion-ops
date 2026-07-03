import httpx
import json
import os
from datetime import datetime, timezone

BABY_API_URL = os.getenv("BABY_API_URL", "http://baby-api:8080")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_title(event_type: str, data: dict) -> str:
    if event_type == "inventory_synced":
        fixed = data.get("fixed_count", 0)
        broken = data.get("broken_count", 0)
        return f"Wix Inventory Sync: {fixed} fixed, {broken} issues found"
    elif event_type == "order_fulfilled":
        count = data.get("fulfilled_count", 0)
        return f"Wix Orders: {count} fulfilled via Zendrop"
    elif event_type == "tracking_updated":
        count = data.get("updated_count", 0)
        return f"Wix Tracking: {count} orders updated"
    elif event_type == "audit_complete":
        broken = data.get("broken_count", 0)
        healthy = data.get("healthy_count", 0)
        return f"Wix Audit: {healthy} healthy, {broken} need fix"
    return f"Wix Agent: {event_type}"


def notify_empire(event_type: str, data: dict) -> None:
    """Fire-and-forget: write to vault inbox + ping n8n for agent routing."""
    payload = {
        "event": event_type,
        "timestamp": _now(),
        "source": "wix-agent",
        **data,
    }

    lane = "20-deals" if event_type == "order_fulfilled" else "10-intel"
    title = _event_title(event_type, data)

    if BABY_API_URL:
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{BABY_API_URL}/vault/inbox",
                    json={"lane": lane, "title": title, "body": json.dumps(payload, indent=2), "tags": ["wix-agent", event_type]},
                )
        except Exception as e:
            print(f"[empire] vault notify failed ({e})")

    if N8N_WEBHOOK_URL:
        try:
            with httpx.Client(timeout=5.0) as client:
                client.post(N8N_WEBHOOK_URL, json=payload)
        except Exception as e:
            print(f"[empire] n8n notify failed ({e})")
