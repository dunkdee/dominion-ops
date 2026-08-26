from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevenueStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    success_event TEXT NOT NULL DEFAULT 'purchase',
                    wix_field TEXT NOT NULL DEFAULT 'plainDescription',
                    control_json TEXT NOT NULL,
                    treatment_json TEXT NOT NULL,
                    treatment_pct INTEGER NOT NULL DEFAULT 50,
                    auto_promote INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    winner TEXT,
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    decided_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_experiment_per_product
                    ON experiments(product_id) WHERE status='active';
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    revenue_cents INTEGER NOT NULL DEFAULT 0,
                    occurred_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(experiment_id) REFERENCES experiments(id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_exp_type
                    ON events(experiment_id,event_type,variant);
                CREATE INDEX IF NOT EXISTS idx_events_exp_visitor
                    ON events(experiment_id,visitor_id,variant,occurred_at);
                CREATE TABLE IF NOT EXISTS promotions (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    field TEXT NOT NULL,
                    before_value TEXT NOT NULL,
                    after_value TEXT NOT NULL,
                    before_revision TEXT NOT NULL,
                    after_revision TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'promoted',
                    created_at TEXT NOT NULL,
                    rolled_back_at TEXT,
                    rollback_revision TEXT,
                    FOREIGN KEY(experiment_id) REFERENCES experiments(id)
                );
                CREATE TABLE IF NOT EXISTS order_reconciliation (
                    order_id TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    visitor_id TEXT,
                    revenue_cents INTEGER NOT NULL DEFAULT 0,
                    reconciled_at TEXT NOT NULL,
                    PRIMARY KEY(order_id,experiment_id)
                );
                """
            )

    def create_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        exp_id = str(payload.get("id") or f"exp_{uuid.uuid4().hex[:12]}")
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO experiments
                (id,name,product_id,target_url,success_event,wix_field,control_json,
                 treatment_json,treatment_pct,auto_promote,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    exp_id,
                    payload["name"],
                    payload["product_id"],
                    payload["target_url"],
                    payload.get("success_event", "purchase"),
                    payload.get("wix_field", "plainDescription"),
                    json.dumps(payload["control"], separators=(",", ":"), sort_keys=True),
                    json.dumps(payload["treatment"], separators=(",", ":"), sort_keys=True),
                    int(payload.get("treatment_pct", 50)),
                    1 if payload.get("auto_promote") else 0,
                    "draft",
                    utc_now(),
                ),
            )
        return self.get_experiment(exp_id)

    def get_experiment(self, exp_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
        if row is None:
            raise KeyError(exp_id)
        out = dict(row)
        out["control"] = json.loads(out.pop("control_json"))
        out["treatment"] = json.loads(out.pop("treatment_json"))
        out["auto_promote"] = bool(out["auto_promote"])
        return out

    def list_experiments(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if status:
                rows = db.execute("SELECT id FROM experiments WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
            else:
                rows = db.execute("SELECT id FROM experiments ORDER BY created_at DESC").fetchall()
        return [self.get_experiment(row["id"]) for row in rows]

    def activate(self, exp_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT status,product_id FROM experiments WHERE id=?", (exp_id,)).fetchone()
            if row is None:
                raise KeyError(exp_id)
            if row["status"] not in {"draft", "paused"}:
                raise ValueError(f"cannot activate from {row['status']}")
            other = db.execute(
                "SELECT id FROM experiments WHERE product_id=? AND status='active' AND id<>?",
                (row["product_id"], exp_id),
            ).fetchone()
            if other:
                raise ValueError(f"product already has active experiment {other['id']}")
            db.execute("UPDATE experiments SET status='active',activated_at=? WHERE id=?", (utc_now(), exp_id))
        return self.get_experiment(exp_id)

    def pause(self, exp_id: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("UPDATE experiments SET status='paused' WHERE id=? AND status='active'", (exp_id,))
        return self.get_experiment(exp_id)

    def record_event(
        self, *, event_id: str, experiment_id: str, visitor_id: str, variant: str,
        event_type: str, revenue_cents: int = 0, metadata: dict[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> bool:
        if variant not in {"control", "treatment"}:
            raise ValueError("invalid variant")
        if revenue_cents < 0:
            raise ValueError("revenue_cents must be non-negative")
        with self._connect() as db:
            result = db.execute(
                """INSERT OR IGNORE INTO events
                (id,experiment_id,visitor_id,variant,event_type,revenue_cents,occurred_at,metadata_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    event_id, experiment_id, visitor_id, variant, event_type, int(revenue_cents),
                    occurred_at or utc_now(), json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
                ),
            )
            return result.rowcount == 1

    def metrics(self, exp_id: str) -> dict[str, dict[str, int]]:
        exp = self.get_experiment(exp_id)
        success_event = exp["success_event"]
        result: dict[str, dict[str, int]] = {}
        with self._connect() as db:
            for variant in ("control", "treatment"):
                def distinct(event_type: str) -> int:
                    row = db.execute(
                        "SELECT COUNT(DISTINCT visitor_id) n FROM events WHERE experiment_id=? AND variant=? AND event_type=?",
                        (exp_id, variant, event_type),
                    ).fetchone()
                    return int(row["n"])
                revenue = db.execute(
                    "SELECT COALESCE(SUM(revenue_cents),0) n FROM events WHERE experiment_id=? AND variant=? AND event_type='purchase'",
                    (exp_id, variant),
                ).fetchone()["n"]
                result[variant] = {
                    "visitors": distinct("impression"),
                    "clicks": distinct("click"),
                    "conversions": distinct(success_event),
                    "revenue_cents": int(revenue),
                }
        return result

    def click_candidates(self, exp_id: str, order_time: str, lookback_minutes: int) -> list[dict[str, str]]:
        end = datetime.fromisoformat(order_time.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        with self._connect() as db:
            rows = db.execute(
                """SELECT visitor_id,variant,MAX(occurred_at) latest
                   FROM events
                   WHERE experiment_id=? AND event_type='click' AND occurred_at>=? AND occurred_at<=?
                   GROUP BY visitor_id,variant ORDER BY latest DESC""",
                (exp_id, start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def reconciliation_exists(self, order_id: str, exp_id: str) -> bool:
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM order_reconciliation WHERE order_id=? AND experiment_id=?",
                (order_id, exp_id),
            ).fetchone() is not None

    def record_reconciliation(
        self, *, order_id: str, exp_id: str, status: str, reason: str,
        visitor_id: str | None = None, revenue_cents: int = 0,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO order_reconciliation
                (order_id,experiment_id,status,reason,visitor_id,revenue_cents,reconciled_at)
                VALUES (?,?,?,?,?,?,?)""",
                (order_id, exp_id, status, reason, visitor_id, int(revenue_cents), utc_now()),
            )

    def mark_decision(self, exp_id: str, status: str, winner: str | None) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE experiments SET status=?,winner=?,decided_at=? WHERE id=?",
                (status, winner, utc_now(), exp_id),
            )

    def record_promotion(
        self, *, experiment_id: str, product_id: str, field: str, before_value: str,
        after_value: str, before_revision: str, after_revision: str,
    ) -> dict[str, Any]:
        promo_id = f"promo_{uuid.uuid4().hex[:12]}"
        with self._connect() as db:
            db.execute(
                """INSERT INTO promotions
                (id,experiment_id,product_id,field,before_value,after_value,before_revision,after_revision,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    promo_id, experiment_id, product_id, field, before_value, after_value,
                    before_revision, after_revision, "promoted", utc_now(),
                ),
            )
            db.execute(
                "UPDATE experiments SET status='promoted',winner='treatment',decided_at=? WHERE id=?",
                (utc_now(), experiment_id),
            )
        return self.get_promotion(promo_id)

    def get_promotion(self, promo_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM promotions WHERE id=?", (promo_id,)).fetchone()
        if row is None:
            raise KeyError(promo_id)
        return dict(row)

    def latest_promotion_for_experiment(self, exp_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM promotions WHERE experiment_id=? AND status='promoted' ORDER BY created_at DESC LIMIT 1",
                (exp_id,),
            ).fetchone()
        if row is None:
            raise KeyError(exp_id)
        return dict(row)

    def mark_rolled_back(self, promo_id: str, rollback_revision: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT experiment_id FROM promotions WHERE id=?", (promo_id,)).fetchone()
            if row is None:
                raise KeyError(promo_id)
            db.execute(
                "UPDATE promotions SET status='rolled_back',rolled_back_at=?,rollback_revision=? WHERE id=? AND status='promoted'",
                (utc_now(), rollback_revision, promo_id),
            )
            db.execute("UPDATE experiments SET status='rolled_back' WHERE id=?", (row["experiment_id"],))
        return self.get_promotion(promo_id)
