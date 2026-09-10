"""Cross-cloud dispatch — GCP decides, Oracle executes, GCP verifies.

Three rules carry the architecture, and each is enforced here rather than
documented and hoped for:

  routing      sensitivity decides where work may run before capability does.
               Constitutional and secret-bearing work never leaves GCP, no
               matter which worker is idle or how the caller asked.
  subordination a worker returns a *claim*. `WorkerResult` is not a state
               change and cannot become one -- only a verified receipt lets
               canonical state move, and verification happens on the GCP side
               in `verify_worker_result`.
  fail-closed  an unverifiable result is UNKNOWN, never DONE. A worker that
               goes silent leaves its task BLOCKED, and GCP truth is untouched.

The envelope fields come from the work order (§8) and are all required: a
dispatch missing its policy revision or deadline is refused rather than sent,
because a receipt that cannot name the policy in force proves nothing later.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from ..agents.workers import Cloud, WorkerError, WorkerRegistry
from ..governance.constitution import Status
from ..logging import redact


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    CONSTITUTIONAL = "constitutional"

    @property
    def may_leave_primary(self) -> bool:
        """Whether work at this classification may run outside GCP."""
        return self in {Sensitivity.PUBLIC, Sensitivity.INTERNAL}


class DispatchRefused(RuntimeError):
    """A dispatch was refused before anything left the control plane."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DispatchEnvelope:
    """What GCP sends a worker. Every field is required by §8."""

    task_id: str
    lane_id: str
    capability: str
    policy_revision: str
    code_revision: str
    deadline: str
    sensitivity: Sensitivity
    expected_receipt_type: str
    payload: dict = field(default_factory=dict)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "lane_id": self.lane_id,
            "capability": self.capability,
            "policy_revision": self.policy_revision,
            "code_revision": self.code_revision,
            "trace_id": self.trace_id,
            "deadline": self.deadline,
            "sensitivity": self.sensitivity.value,
            "expected_receipt_type": self.expected_receipt_type,
            "payload": self.payload,
        }

    @property
    def expired(self) -> bool:
        try:
            deadline = datetime.fromisoformat(self.deadline)
        except ValueError:
            return True
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return _now() > deadline


@dataclass(frozen=True)
class WorkerResult:
    """What a worker returns. A claim, not a state change."""

    task_id: str
    worker_id: str
    cloud: Cloud
    status: str
    output: str
    output_hash: str
    started_at: str
    completed_at: str
    model_identity: str = ""
    error_classification: str = ""
    sanitized: bool = False
    trace_id: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "cloud": self.cloud.value,
            "status": self.status,
            "output_hash": self.output_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "model_identity": self.model_identity,
            "error_classification": self.error_classification,
            "sanitized": self.sanitized,
            "trace_id": self.trace_id,
        }


def hash_output(output: str) -> str:
    return hashlib.sha256(output.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Verification:
    accepted: bool
    status: Status
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "status": self.status.value,
            "reasons": list(self.reasons),
        }


class CrossCloudDispatcher:
    """GCP-side dispatcher. The only component that may target another cloud."""

    def __init__(
        self,
        workers: WorkerRegistry,
        *,
        policy_revision: str,
        code_revision: str,
        default_deadline_seconds: int = 300,
    ) -> None:
        self.workers = workers
        self.policy_revision = policy_revision
        self.code_revision = code_revision
        self.default_deadline_seconds = default_deadline_seconds

    # ── routing ─────────────────────────────────────────────────────────

    def select_worker(
        self,
        capability: str,
        sensitivity: Sensitivity,
        *,
        prefer_cloud: Cloud | None = None,
    ) -> str:
        """Choose a worker, or refuse. Sensitivity is checked before capability.

        Order matters: asking "may this work leave GCP?" before "who can do
        it?" means a sensitive task can never be routed off-primary just
        because the only capable worker happens to be remote.
        """
        candidates = [w for w in self.workers.all() if w.usable]
        if not candidates:
            raise DispatchRefused("no usable worker is registered")

        if not sensitivity.may_leave_primary:
            candidates = [w for w in candidates if w.cloud.is_primary]
            if not candidates:
                raise DispatchRefused(
                    f"work classified '{sensitivity.value}' may not leave the primary "
                    "cloud, and no primary-cloud worker is available"
                )

        if prefer_cloud is not None:
            preferred = [w for w in candidates if w.cloud is prefer_cloud]
            if preferred:
                candidates = preferred

        # Deterministic code first, then primary cloud, then subordinate --
        # cheapest trustworthy option wins, and ties break the same way twice.
        candidates.sort(key=lambda w: (not w.cloud.is_primary, w.worker_id))

        for worker in candidates:
            permitted, _ = self.workers.permits(worker.worker_id, capability)
            if permitted:
                return worker.worker_id

        raise DispatchRefused(
            f"no usable worker is permitted to execute capability '{capability}'"
        )

    # ── dispatch ────────────────────────────────────────────────────────

    def build_envelope(
        self,
        *,
        worker_id: str,
        task_id: str,
        lane_id: str,
        capability: str,
        sensitivity: Sensitivity,
        expected_receipt_type: str,
        payload: dict | None = None,
        deadline_seconds: int | None = None,
    ) -> DispatchEnvelope:
        """Build and authorize one dispatch. Refuses rather than sends.

        Registry failures are translated into DispatchRefused so a caller has
        exactly one exception to handle: leaking WorkerError meant a caller
        guarding against refusal still crashed when the worker was revoked.
        """
        try:
            worker = self.workers.require_usable(worker_id)
        except WorkerError as exc:
            raise DispatchRefused(str(exc)) from exc

        if not sensitivity.may_leave_primary and not worker.cloud.is_primary:
            raise DispatchRefused(
                f"refusing to send '{sensitivity.value}' work to {worker.cloud.value}: "
                "only the primary cloud may hold work at this classification"
            )

        permitted, reason = self.workers.permits(worker_id, capability)
        if not permitted:
            raise DispatchRefused(reason)

        if not self.policy_revision:
            raise DispatchRefused(
                "refusing to dispatch without a policy revision; a receipt that cannot "
                "name the policy in force proves nothing"
            )

        seconds = deadline_seconds or self.default_deadline_seconds
        deadline = (_now() + timedelta(seconds=seconds)).isoformat()

        # The payload crosses a cloud boundary. Redact before it leaves.
        safe_payload = {
            key: redact(value) if isinstance(value, str) else value
            for key, value in (payload or {}).items()
        }

        return DispatchEnvelope(
            task_id=task_id,
            lane_id=lane_id,
            capability=capability,
            policy_revision=self.policy_revision,
            code_revision=self.code_revision,
            deadline=deadline,
            sensitivity=sensitivity,
            expected_receipt_type=expected_receipt_type,
            payload=safe_payload,
        )

    # ── verification ────────────────────────────────────────────────────

    def verify_worker_result(
        self,
        envelope: DispatchEnvelope,
        result: WorkerResult | None,
    ) -> Verification:
        """Decide whether a worker's claim may move canonical state.

        Fail-closed throughout. Every path that cannot prove the result
        returns UNKNOWN or BLOCKED; none returns DONE by default.
        """
        reasons: list[str] = []

        # No result at all: the worker went silent or the deadline passed.
        if result is None:
            return Verification(
                accepted=False,
                status=Status.BLOCKED,
                reasons=("worker returned no result; task is blocked, GCP state unchanged",),
            )

        if result.task_id != envelope.task_id:
            reasons.append("result task_id does not match the dispatched task")

        try:
            worker = self.workers.require_usable(result.worker_id)
        except WorkerError as exc:
            # A revoked worker's late result must not be accepted.
            return Verification(
                accepted=False,
                status=Status.BLOCKED,
                reasons=(f"result rejected: {exc}",),
            )

        if worker.cloud is not result.cloud:
            reasons.append(
                f"result claims cloud '{result.cloud.value}' but worker is registered "
                f"in '{worker.cloud.value}'"
            )

        if not result.sanitized:
            reasons.append("result is not marked sanitized")

        if result.output_hash != hash_output(result.output):
            reasons.append("output hash does not match the returned output")

        if envelope.expired:
            reasons.append("result arrived after the dispatch deadline")

        if result.status != "DONE":
            reasons.append(f"worker reported status '{result.status}', not DONE")

        # A remote worker's output must never carry a secret back into GCP.
        from ..models.router import scan_for_secrets

        if scan_for_secrets(result.output):
            return Verification(
                accepted=False,
                status=Status.BLOCKED,
                reasons=("returned output contains a secret-shaped value; rejected",),
            )

        if reasons:
            # Unprovable is UNKNOWN; contradicted is BLOCKED.
            contradicted = any(
                "does not match" in r or "rejected" in r or "registered in" in r
                for r in reasons
            )
            return Verification(
                accepted=False,
                status=Status.BLOCKED if contradicted else Status.UNKNOWN,
                reasons=tuple(reasons),
            )

        self.workers.mark_seen(result.worker_id)
        return Verification(
            accepted=True,
            status=Status.DONE,
            reasons=("worker result verified against the dispatch envelope",),
        )


def worker_should_fail_closed(control_plane_reachable: bool) -> tuple[bool, str]:
    """Oracle-side rule: no control plane, no work.

    Stated here, on the GCP side, so both halves compile against one
    definition rather than two that can drift apart.
    """
    if control_plane_reachable:
        return False, "control plane reachable; normal operation"
    return True, (
        "GCP control plane is unreachable; worker fails closed -- no publishing, "
        "no trading, no production merge, no governance mutation"
    )
