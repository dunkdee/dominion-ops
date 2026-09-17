from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _guid(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(uuid.UUID(text))
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc


class AttributionBridgeStore:
    """Same-database bridge from a Dominion click to Wix-native purchase identity."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS attribution_bridge_tokens (
                    token_hash TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_attribution_bridge_token_exp
                    ON attribution_bridge_tokens(experiment_id,expires_at);
                CREATE TABLE IF NOT EXISTS attribution_bridge_links (
                    experiment_id TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    link_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    variant TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY(experiment_id,link_type,link_id)
                );
                CREATE INDEX IF NOT EXISTS idx_attribution_bridge_visitor
                    ON attribution_bridge_links(experiment_id,visitor_id,variant);
                """
            )

    def issue_token(
        self,
        *,
        experiment_id: str,
        visitor_id: str,
        variant: str,
        ttl_minutes: int = 60,
    ) -> str:
        if variant not in {"control", "treatment"}:
            raise ValueError("invalid variant")
        if ttl_minutes < 1 or ttl_minutes > 240:
            raise ValueError("invalid bridge token TTL")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        issued = _utc_now()
        expires = issued + timedelta(minutes=ttl_minutes)
        with self._connect() as db:
            db.execute(
                """INSERT INTO attribution_bridge_tokens
                (token_hash,experiment_id,visitor_id,variant,issued_at,expires_at,used_at)
                VALUES (?,?,?,?,?,?,NULL)""",
                (
                    token_hash,
                    experiment_id,
                    visitor_id,
                    variant,
                    _iso(issued),
                    _iso(expires),
                ),
            )
        return token

    def bind_token(
        self,
        *,
        token: str,
        expected_experiment_id: str,
        purchase_flow_id: str = "",
        checkout_id: str = "",
    ) -> dict[str, Any]:
        purchase_flow_id = _guid(purchase_flow_id, "purchase_flow_id")
        checkout_id = _guid(checkout_id, "checkout_id")
        links = []
        if purchase_flow_id:
            links.append(("purchase_flow", purchase_flow_id))
        if checkout_id:
            links.append(("checkout", checkout_id))
        if not links:
            raise ValueError("purchase_flow_id or checkout_id is required")
        if not expected_experiment_id:
            raise ValueError("expected experiment is required")

        token_hash = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
        now = _utc_now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT token_hash,experiment_id,visitor_id,variant,expires_at,used_at
                   FROM attribution_bridge_tokens WHERE token_hash=?""",
                (token_hash,),
            ).fetchone()
            if row is None:
                raise ValueError("invalid bridge token")
            if str(row["experiment_id"]) != expected_experiment_id:
                raise ValueError("bridge token experiment mismatch")
            if row["used_at"]:
                raise ValueError("bridge token already used")
            expires = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                raise ValueError("bridge token expired")

            for link_type, link_id in links:
                existing = db.execute(
                    """SELECT visitor_id,variant FROM attribution_bridge_links
                       WHERE experiment_id=? AND link_type=? AND link_id=?""",
                    (row["experiment_id"], link_type, link_id),
                ).fetchone()
                if existing and (
                    existing["visitor_id"] != row["visitor_id"]
                    or existing["variant"] != row["variant"]
                ):
                    raise ValueError("Wix purchase identity already linked")
                db.execute(
                    """INSERT OR IGNORE INTO attribution_bridge_links
                    (experiment_id,link_type,link_id,visitor_id,variant,linked_at)
                    VALUES (?,?,?,?,?,?)""",
                    (
                        row["experiment_id"],
                        link_type,
                        link_id,
                        row["visitor_id"],
                        row["variant"],
                        _iso(now),
                    ),
                )
            db.execute(
                "UPDATE attribution_bridge_tokens SET used_at=? WHERE token_hash=?",
                (_iso(now), token_hash),
            )
            return {
                "experiment_id": str(row["experiment_id"]),
                "visitor_id": str(row["visitor_id"]),
                "variant": str(row["variant"]),
                "bound": [link_type for link_type, _ in links],
            }

    def order_links(
        self,
        *,
        experiment_id: str,
        purchase_flow_id: str = "",
        checkout_id: str = "",
    ) -> list[dict[str, str]]:
        specs: list[tuple[str, str]] = []
        if purchase_flow_id:
            specs.append(("purchase_flow", _guid(purchase_flow_id, "purchase_flow_id")))
        if checkout_id:
            specs.append(("checkout", _guid(checkout_id, "checkout_id")))
        if not specs:
            return []
        out: list[dict[str, str]] = []
        with self._connect() as db:
            for link_type, link_id in specs:
                row = db.execute(
                    """SELECT experiment_id,link_type,link_id,visitor_id,variant,linked_at
                       FROM attribution_bridge_links
                       WHERE experiment_id=? AND link_type=? AND link_id=?""",
                    (experiment_id, link_type, link_id),
                ).fetchone()
                if row is not None:
                    out.append(dict(row))
        return out
