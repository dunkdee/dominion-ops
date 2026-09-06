from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .models import PublishJob, PublishReceipt, PublishStatus, utc_now


class PublisherAdapter(Protocol):
    platform: str

    def validate_credentials(self, account_id: str) -> None: ...
    def validate_job(self, job: PublishJob) -> None: ...
    def publish(self, job: PublishJob) -> str: ...


class PublisherStore:
    """SQLite-backed durable queue and immutable receipt ledger."""

    def __init__(self, path: str | Path = "publisher.db") -> None:
        self.path = str(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    idempotency_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def upsert_job(self, job: PublishJob, status: PublishStatus) -> None:
        now = utc_now()
        payload = json.dumps(asdict(job), sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(idempotency_key, payload, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    payload=excluded.payload,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (job.idempotency_key, payload, status.value, now, now),
            )
            conn.commit()

    def status_for(self, idempotency_key: str) -> PublishStatus | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return PublishStatus(row["status"]) if row else None

    def write_receipt(self, receipt: PublishReceipt) -> None:
        payload = asdict(receipt)
        payload["status"] = receipt.status.value
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO receipts(receipt_id, idempotency_key, payload, created_at) VALUES(?, ?, ?, ?)",
                (
                    receipt.receipt_id,
                    receipt.idempotency_key,
                    json.dumps(payload, sort_keys=True),
                    receipt.observed_at,
                ),
            )
            conn.commit()

    def receipts_for(self, idempotency_key: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM receipts WHERE idempotency_key = ? ORDER BY created_at",
                (idempotency_key,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]


class PublisherCore:
    def __init__(self, store: PublisherStore, adapters: dict[str, PublisherAdapter] | None = None) -> None:
        self.store = store
        self.adapters = {k.lower(): v for k, v in (adapters or {}).items()}

    def register_adapter(self, adapter: PublisherAdapter) -> None:
        self.adapters[adapter.platform.lower()] = adapter

    def queue(self, job: PublishJob) -> PublishReceipt:
        job.validate()
        job.require_approval()
        existing = self.store.status_for(job.idempotency_key)
        if existing in {PublishStatus.QUEUED, PublishStatus.PUBLISHED}:
            receipt = self._receipt(job, existing, error="duplicate suppressed")
            self.store.write_receipt(receipt)
            return receipt
        self.store.upsert_job(job, PublishStatus.QUEUED)
        receipt = self._receipt(job, PublishStatus.QUEUED)
        self.store.write_receipt(receipt)
        return receipt

    def publish(self, job: PublishJob) -> PublishReceipt:
        job.validate()
        job.require_approval()

        existing = self.store.status_for(job.idempotency_key)
        if existing == PublishStatus.PUBLISHED:
            receipt = self._receipt(job, PublishStatus.PUBLISHED, error="duplicate suppressed")
            self.store.write_receipt(receipt)
            return receipt

        adapter = self.adapters.get(job.platform.lower())
        if adapter is None:
            receipt = self._receipt(job, PublishStatus.BLOCKED, error="platform adapter is not registered")
            self.store.upsert_job(job, PublishStatus.BLOCKED)
            self.store.write_receipt(receipt)
            return receipt

        try:
            adapter.validate_credentials(job.account_id)
            adapter.validate_job(job)
            provider_post_id = adapter.publish(job)
        except Exception as exc:
            receipt = self._receipt(job, PublishStatus.FAILED, error=str(exc))
            self.store.upsert_job(job, PublishStatus.FAILED)
            self.store.write_receipt(receipt)
            return receipt

        self.store.upsert_job(job, PublishStatus.PUBLISHED)
        receipt = self._receipt(job, PublishStatus.PUBLISHED, provider_post_id=provider_post_id)
        self.store.write_receipt(receipt)
        return receipt

    def _receipt(
        self,
        job: PublishJob,
        status: PublishStatus,
        provider_post_id: str | None = None,
        error: str | None = None,
    ) -> PublishReceipt:
        return PublishReceipt(
            receipt_id=str(uuid.uuid4()),
            idempotency_key=job.idempotency_key,
            campaign_id=job.campaign_id,
            platform=job.platform.lower(),
            account_id=job.account_id,
            status=status,
            observed_at=utc_now(),
            asset_hashes=tuple(sorted(a.sha256.lower() for a in job.assets)),
            destination_url=job.attributed_url(),
            provider_post_id=provider_post_id,
            error=error,
        )
