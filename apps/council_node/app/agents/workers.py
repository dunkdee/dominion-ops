"""Worker registry — subordinate compute, including other clouds.

An agent decides; a worker executes. This registry holds the second kind, and
its whole purpose is to keep them subordinate:

  worker_only authority   a worker may never declare production truth. Its
                          output is a claim that GCP verifies, never a state
                          change it performs.
  revocable from GCP      revocation is immediate and local to this registry,
                          so a compromised or misbehaving worker is cut off
                          without needing the worker's cooperation.
  capability bounded      the same allow/deny model as agents, plus a set of
                          capabilities no remote worker may ever hold.

The forbidden set is deliberately wider for remote workers than for local
agents. A worker sits in another cloud, on hardware Dominion does not own the
whole trust path to, so publishing, merging and governance mutation are off
the table regardless of what its registration asks for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

GOVERNANCE_NAME = "RADAH_MEMSHALAH"

# No remote worker may hold these, in any cloud, under any registration.
# Superset of the agent-level denials: a worker is further from the control
# plane, so its ceiling is lower.
WORKER_FORBIDDEN = frozenset({
    "shell.unrestricted",
    "secret_readback",
    "financial_transfer",
    "credential.export",
    "governance.modify",
    "governance_mutation",
    "production_merge",
    "publish_without_gate",
    "lane_status.write",
    "canonical_state.write",
})


class WorkerError(RuntimeError):
    """A worker registration or dispatch was refused."""


class Cloud(str, Enum):
    GCP = "gcp"
    ORACLE = "oracle"

    @property
    def is_primary(self) -> bool:
        """GCP is the control plane. Everything else is subordinate."""
        return self is Cloud.GCP


class WorkerRole(str, Enum):
    LOCAL_MODEL = "local_model_worker"
    RESEARCH = "research_worker"
    CONTENT = "content_worker"
    BATCH = "batch_worker"
    EXPERIMENT = "experiment_worker"


class WorkerState(str, Enum):
    ENABLED = "ENABLED"
    REVOKED = "REVOKED"
    UNREACHABLE = "UNREACHABLE"


@dataclass
class WorkerRecord:
    worker_id: str
    cloud: Cloud
    role: WorkerRole
    allowed_capabilities: tuple[str, ...] = field(default_factory=tuple)
    forbidden_capabilities: tuple[str, ...] = field(default_factory=tuple)
    governance: str = GOVERNANCE_NAME
    authority: str = "worker_only"
    state: WorkerState = WorkerState.ENABLED
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    revoked_at: str | None = None
    revoked_reason: str = ""
    last_seen_at: str | None = None

    @property
    def usable(self) -> bool:
        return self.state is WorkerState.ENABLED

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "cloud": self.cloud.value,
            "role": self.role.value,
            "authority": self.authority,
            "governance": self.governance,
            "allowed_capabilities": list(self.allowed_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "state": self.state.value,
            "registered_at": self.registered_at,
            "revoked_at": self.revoked_at,
            "revoked_reason": self.revoked_reason,
            "last_seen_at": self.last_seen_at,
        }


class WorkerRegistry:
    """GCP-side registry. The only place a worker becomes usable."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerRecord] = {}

    # ── registration ────────────────────────────────────────────────────

    def register(self, record: WorkerRecord) -> WorkerRecord:
        if record.governance != GOVERNANCE_NAME:
            raise WorkerError(
                f"worker '{record.worker_id}' does not declare {GOVERNANCE_NAME} governance"
            )
        if record.authority != "worker_only":
            raise WorkerError(
                f"worker '{record.worker_id}' claims authority '{record.authority}'; "
                "remote workers are worker_only"
            )
        overreach = set(record.allowed_capabilities) & WORKER_FORBIDDEN
        if overreach:
            raise WorkerError(
                f"worker '{record.worker_id}' requests capabilities no remote worker "
                f"may hold: {sorted(overreach)}"
            )
        if record.worker_id in self._workers:
            raise WorkerError(f"worker '{record.worker_id}' is already registered")
        self._workers[record.worker_id] = record
        return record

    # ── revocation ──────────────────────────────────────────────────────

    def revoke(self, worker_id: str, reason: str) -> WorkerRecord:
        """Cut a worker off. Takes effect immediately and locally.

        Revocation does not ask the worker to stand down -- it stops GCP from
        dispatching to it and stops its receipts being accepted. A worker that
        keeps running is simply talking to nobody.
        """
        record = self._workers.get(worker_id)
        if record is None:
            raise WorkerError(f"worker '{worker_id}' is not registered")
        record.state = WorkerState.REVOKED
        record.revoked_at = datetime.now(timezone.utc).isoformat()
        record.revoked_reason = reason
        return record

    def reinstate(self, worker_id: str) -> WorkerRecord:
        record = self._workers.get(worker_id)
        if record is None:
            raise WorkerError(f"worker '{worker_id}' is not registered")
        record.state = WorkerState.ENABLED
        record.revoked_at = None
        record.revoked_reason = ""
        return record

    def mark_unreachable(self, worker_id: str) -> WorkerRecord:
        """Health, not authority. An unreachable worker is not a revoked one."""
        record = self._workers.get(worker_id)
        if record is None:
            raise WorkerError(f"worker '{worker_id}' is not registered")
        if record.state is not WorkerState.REVOKED:
            record.state = WorkerState.UNREACHABLE
        return record

    def mark_seen(self, worker_id: str) -> None:
        record = self._workers.get(worker_id)
        if record is None:
            return
        record.last_seen_at = datetime.now(timezone.utc).isoformat()
        if record.state is WorkerState.UNREACHABLE:
            record.state = WorkerState.ENABLED

    # ── lookup ──────────────────────────────────────────────────────────

    def get(self, worker_id: str) -> WorkerRecord | None:
        return self._workers.get(worker_id)

    def require_usable(self, worker_id: str) -> WorkerRecord:
        record = self.get(worker_id)
        if record is None:
            raise WorkerError(f"worker '{worker_id}' is not registered")
        if record.state is WorkerState.REVOKED:
            raise WorkerError(
                f"worker '{worker_id}' is revoked: {record.revoked_reason or 'no reason recorded'}"
            )
        if record.state is WorkerState.UNREACHABLE:
            raise WorkerError(f"worker '{worker_id}' is unreachable")
        return record

    def all(self) -> list[WorkerRecord]:
        return [self._workers[k] for k in sorted(self._workers)]

    def by_cloud(self, cloud: Cloud) -> list[WorkerRecord]:
        return [w for w in self.all() if w.cloud is cloud]

    def permits(self, worker_id: str, capability_id: str) -> tuple[bool, str]:
        """Return (permitted, reason). Denials always carry a reason."""
        try:
            record = self.require_usable(worker_id)
        except WorkerError as exc:
            return False, str(exc)

        if capability_id in WORKER_FORBIDDEN:
            return False, (
                f"capability '{capability_id}' may never be executed by a remote worker"
            )
        if capability_id in record.forbidden_capabilities:
            return False, f"capability '{capability_id}' is forbidden for this worker"
        if capability_id not in record.allowed_capabilities:
            return False, f"capability '{capability_id}' is not granted to this worker"
        return True, "granted"

    # ── persistence ─────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path | str) -> "WorkerRegistry":
        p = Path(path).expanduser()
        if not p.is_file():
            raise WorkerError(f"worker registry file is missing: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        registry = cls()
        for row in data.get("workers", []):
            registry.register(WorkerRecord(
                worker_id=str(row["worker_id"]),
                cloud=Cloud(row.get("cloud", "oracle")),
                role=WorkerRole(row.get("role", "batch_worker")),
                allowed_capabilities=tuple(row.get("allowed_capabilities", [])),
                forbidden_capabilities=tuple(row.get("forbidden_capabilities", [])),
                governance=str(row.get("governance", GOVERNANCE_NAME)),
                authority=str(row.get("authority", "worker_only")),
                state=WorkerState(row.get("state", "ENABLED")),
            ))
        return registry
