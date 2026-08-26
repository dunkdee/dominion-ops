from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import settings

_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        settings.db_path,
        timeout=15,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=FULL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


@contextmanager
def tx(write: bool = False):
    """
    Serializable-enough local transaction boundary for a single service
    instance. For horizontal scale, swap this adapter for PostgreSQL while
    keeping the service API unchanged.
    """
    with _lock:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE;" if write else "BEGIN;")
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()


def init_db() -> None:
    with tx(write=True) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            demand REAL NOT NULL CHECK(demand BETWEEN 0 AND 10),
            buyer_intent REAL NOT NULL CHECK(buyer_intent BETWEEN 0 AND 10),
            urgency REAL NOT NULL CHECK(urgency BETWEEN 0 AND 10),
            competition REAL NOT NULL CHECK(competition BETWEEN 0 AND 10),
            scalability REAL NOT NULL CHECK(scalability BETWEEN 0 AND 10),
            defensibility REAL NOT NULL CHECK(defensibility BETWEEN 0 AND 10),
            execution_ease REAL NOT NULL CHECK(execution_ease BETWEEN 0 AND 10),
            payout REAL NOT NULL CHECK(payout >= 0),
            conversion_rate REAL NOT NULL CHECK(conversion_rate BETWEEN 0 AND 1),
            opportunity_score REAL NOT NULL CHECK(opportunity_score BETWEEN 0 AND 10),
            expected_rpv REAL NOT NULL CHECK(expected_rpv >= 0),
            status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK(status IN ('ACTIVE','PAUSED','REJECTED')),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            opportunity_slug TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source TEXT,
            medium TEXT,
            campaign TEXT,
            page TEXT,
            revenue REAL NOT NULL DEFAULT 0 CHECK(revenue >= 0),
            occurred_at INTEGER NOT NULL,
            recorded_at INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_events_slug_time
            ON events(opportunity_slug, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(event_type);

        CREATE TABLE IF NOT EXISTS radah_decisions (
            decision_id TEXT PRIMARY KEY,
            correlation_id TEXT NOT NULL UNIQUE,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('ALLOW','HOLD','DENY')),
            reason TEXT NOT NULL,
            authority_version TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            issued_at INTEGER NOT NULL,
            payload_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id TEXT NOT NULL UNIQUE,
            correlation_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            result TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_corr
            ON audit_log(correlation_id);

        CREATE TABLE IF NOT EXISTS childcare_leads (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            business_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            work_email TEXT NOT NULL,
            state TEXT NOT NULL,
            county TEXT,
            employee_count INTEGER,
            estimated_annual_childcare_budget REAL,
            company_website TEXT,
            consent_recorded INTEGER NOT NULL CHECK(consent_recorded IN (0,1)),
            status TEXT NOT NULL DEFAULT 'PENDING_RADAH_HANDOFF'
                CHECK(status IN ('PENDING_RADAH_HANDOFF','REFERRED','CLOSED','PURGED')),
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_childcare_leads_status
            ON childcare_leads(status, created_at);

        CREATE TABLE IF NOT EXISTS childcare_handoffs (
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            destination_url TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            radah_correlation_id TEXT NOT NULL UNIQUE,
            published_reward_usd REAL NOT NULL CHECK(published_reward_usd >= 0),
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            first_clicked_at INTEGER,
            converted_at INTEGER,
            confirmed_reward_usd REAL,
            provider_receipt_id TEXT,
            FOREIGN KEY(lead_id) REFERENCES childcare_leads(id)
        );

        CREATE INDEX IF NOT EXISTS idx_childcare_handoffs_lead
            ON childcare_handoffs(lead_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_childcare_handoffs_expiry
            ON childcare_handoffs(expires_at);
        """)
