"""Cross-cloud subordination (work order v2.0, §6/§7/§12/§19).

The architecture rests on one claim: Oracle can do work but cannot declare
truth. These tests attack that claim from every direction a real failure
would — a revoked worker returning a late result, a forged output hash, a
worker lying about which cloud it is in, sensitive work looking for a route
off-primary, and the control plane going dark.

Every assertion here is a refusal. That is the point: the value of a
subordinate worker tier is entirely in what it is prevented from doing.
"""

from __future__ import annotations

import pytest

from apps.council_node.app.agents.workers import (
    Cloud, WorkerError, WorkerRecord, WorkerRegistry, WorkerRole, WorkerState,
)
from apps.council_node.app.orchestration.dispatch import (
    CrossCloudDispatcher, DispatchRefused, Sensitivity, WorkerResult,
    hash_output, worker_should_fail_closed,
)

POLICY = "a941eb9d7befac62"
CODE = "6c6b0ad"


@pytest.fixture
def registry() -> WorkerRegistry:
    r = WorkerRegistry()
    r.register(WorkerRecord(
        worker_id="gcp-local-01", cloud=Cloud.GCP, role=WorkerRole.BATCH,
        allowed_capabilities=("summarize", "classify", "research_synthesis"),
    ))
    r.register(WorkerRecord(
        worker_id="oracle-ollama-01", cloud=Cloud.ORACLE, role=WorkerRole.LOCAL_MODEL,
        allowed_capabilities=("summarize", "classify", "draft_content", "research_synthesis"),
    ))
    return r


@pytest.fixture
def dispatcher(registry) -> CrossCloudDispatcher:
    return CrossCloudDispatcher(registry, policy_revision=POLICY, code_revision=CODE)


def _envelope(dispatcher, worker_id="oracle-ollama-01", capability="summarize",
              sensitivity=Sensitivity.INTERNAL, **kw):
    return dispatcher.build_envelope(
        worker_id=worker_id, task_id="t-1", lane_id="traffic",
        capability=capability, sensitivity=sensitivity,
        expected_receipt_type="research_summary", **kw,
    )


def _result(envelope, output="a summary", worker_id="oracle-ollama-01",
            cloud=Cloud.ORACLE, status="DONE", **kw):
    fields = dict(
        task_id=envelope.task_id, worker_id=worker_id, cloud=cloud, status=status,
        output=output, output_hash=hash_output(output),
        started_at="2026-09-10T00:00:00+00:00",
        completed_at="2026-09-10T00:00:05+00:00",
        model_identity="qwen2.5:7b", sanitized=True, trace_id=envelope.trace_id,
    )
    fields.update(kw)
    return WorkerResult(**fields)


# ── registration keeps workers subordinate ──────────────────────────────

def test_worker_cannot_register_with_control_plane_capabilities(registry):
    for capability in ("production_merge", "governance_mutation", "canonical_state.write"):
        with pytest.raises(WorkerError, match="no remote worker"):
            registry.register(WorkerRecord(
                worker_id=f"rogue-{capability}", cloud=Cloud.ORACLE,
                role=WorkerRole.BATCH, allowed_capabilities=(capability,),
            ))


def test_worker_cannot_claim_more_than_worker_only_authority(registry):
    with pytest.raises(WorkerError, match="worker_only"):
        registry.register(WorkerRecord(
            worker_id="ambitious", cloud=Cloud.ORACLE, role=WorkerRole.BATCH,
            authority="executing",
        ))


def test_worker_must_declare_radah_memshalah(registry):
    with pytest.raises(WorkerError, match="governance"):
        registry.register(WorkerRecord(
            worker_id="ungoverned", cloud=Cloud.ORACLE, role=WorkerRole.BATCH,
            governance="SOMETHING_ELSE",
        ))


def test_forbidden_capabilities_are_denied_even_if_somehow_granted(registry):
    """Belt and braces: the check is enforced at permits(), not only at register()."""
    worker = registry.get("oracle-ollama-01")
    object.__setattr__(worker, "allowed_capabilities",
                       worker.allowed_capabilities + ("production_merge",))
    permitted, reason = registry.permits("oracle-ollama-01", "production_merge")
    assert not permitted
    assert "may never be executed by a remote worker" in reason


# ── revocation is immediate and unilateral ──────────────────────────────

def test_revoked_worker_cannot_be_dispatched_to(registry, dispatcher):
    registry.revoke("oracle-ollama-01", "suspected compromise")
    with pytest.raises(DispatchRefused):
        _envelope(dispatcher, worker_id="oracle-ollama-01")


def test_revoked_worker_late_result_is_rejected(registry, dispatcher):
    """The dangerous case: dispatched, then revoked, then it answers."""
    envelope = _envelope(dispatcher)
    result = _result(envelope)
    registry.revoke("oracle-ollama-01", "revoked mid-flight")

    verification = dispatcher.verify_worker_result(envelope, result)
    assert not verification.accepted
    assert verification.status.value == "BLOCKED"
    assert any("revoked" in r for r in verification.reasons)


def test_revocation_is_reversible(registry):
    registry.revoke("oracle-ollama-01", "temporary")
    registry.reinstate("oracle-ollama-01")
    assert registry.require_usable("oracle-ollama-01").usable


def test_unreachable_is_health_not_authority(registry):
    registry.mark_unreachable("oracle-ollama-01")
    assert registry.get("oracle-ollama-01").state is WorkerState.UNREACHABLE
    registry.mark_seen("oracle-ollama-01")
    assert registry.get("oracle-ollama-01").state is WorkerState.ENABLED


def test_marking_seen_never_resurrects_a_revoked_worker(registry):
    registry.revoke("oracle-ollama-01", "compromised")
    registry.mark_seen("oracle-ollama-01")
    assert registry.get("oracle-ollama-01").state is WorkerState.REVOKED


# ── routing: sensitivity decides before capability ──────────────────────

def test_sensitive_work_never_leaves_the_primary_cloud(dispatcher):
    chosen = dispatcher.select_worker("summarize", Sensitivity.SENSITIVE)
    assert chosen == "gcp-local-01"


def test_constitutional_work_never_leaves_the_primary_cloud(dispatcher):
    chosen = dispatcher.select_worker("summarize", Sensitivity.CONSTITUTIONAL)
    assert chosen == "gcp-local-01"


def test_sensitive_work_is_refused_when_only_oracle_can_do_it(registry, dispatcher):
    """Capability must not be able to override classification."""
    registry.revoke("gcp-local-01", "primary worker down")
    with pytest.raises(DispatchRefused, match="may not leave the primary"):
        dispatcher.select_worker("draft_content", Sensitivity.SENSITIVE)


def test_explicit_dispatch_of_sensitive_work_to_oracle_is_refused(dispatcher):
    with pytest.raises(DispatchRefused, match="only the primary cloud"):
        _envelope(dispatcher, worker_id="oracle-ollama-01",
                  sensitivity=Sensitivity.CONSTITUTIONAL)


def test_internal_work_may_use_oracle(dispatcher):
    envelope = _envelope(dispatcher, capability="draft_content")
    assert envelope.sensitivity is Sensitivity.INTERNAL
    assert envelope.policy_revision == POLICY


def test_primary_cloud_is_preferred_when_both_are_capable(dispatcher):
    assert dispatcher.select_worker("summarize", Sensitivity.PUBLIC) == "gcp-local-01"


def test_ungranted_capability_finds_no_worker(dispatcher):
    with pytest.raises(DispatchRefused, match="no usable worker is permitted"):
        dispatcher.select_worker("financial_transfer", Sensitivity.PUBLIC)


# ── the envelope carries what a receipt needs ───────────────────────────

def test_dispatch_without_a_policy_revision_is_refused(registry):
    blind = CrossCloudDispatcher(registry, policy_revision="", code_revision=CODE)
    with pytest.raises(DispatchRefused, match="policy revision"):
        _envelope(blind)


def test_payload_is_redacted_before_it_crosses_the_boundary(dispatcher):
    envelope = _envelope(dispatcher, payload={
        "brief": "analyse this, key sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGG",
    })
    assert "sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGG" not in envelope.payload["brief"]


# ── verification: a claim is not a state change ─────────────────────────

def test_verified_result_is_accepted(dispatcher):
    envelope = _envelope(dispatcher)
    verification = dispatcher.verify_worker_result(envelope, _result(envelope))
    assert verification.accepted
    assert verification.status.value == "DONE"


def test_silent_worker_blocks_rather_than_completing(dispatcher):
    """Oracle loss must never advance GCP state."""
    envelope = _envelope(dispatcher)
    verification = dispatcher.verify_worker_result(envelope, None)
    assert not verification.accepted
    assert verification.status.value == "BLOCKED"


def test_forged_output_hash_is_rejected(dispatcher):
    envelope = _envelope(dispatcher)
    tampered = _result(envelope, output="the real output")
    object.__setattr__(tampered, "output", "something else entirely")

    verification = dispatcher.verify_worker_result(envelope, tampered)
    assert not verification.accepted
    assert any("hash does not match" in r for r in verification.reasons)


def test_worker_lying_about_its_cloud_is_rejected(dispatcher):
    envelope = _envelope(dispatcher)
    liar = _result(envelope, cloud=Cloud.GCP)
    verification = dispatcher.verify_worker_result(envelope, liar)
    assert not verification.accepted
    assert any("claims cloud" in r for r in verification.reasons)


def test_unsanitized_result_is_not_accepted(dispatcher):
    envelope = _envelope(dispatcher)
    verification = dispatcher.verify_worker_result(envelope, _result(envelope, sanitized=False))
    assert not verification.accepted


def test_result_for_a_different_task_is_rejected(dispatcher):
    envelope = _envelope(dispatcher)
    wrong = _result(envelope)
    object.__setattr__(wrong, "task_id", "some-other-task")
    verification = dispatcher.verify_worker_result(envelope, wrong)
    assert not verification.accepted


def test_secret_bearing_output_is_rejected_outright(dispatcher):
    """A worker must not be able to carry a credential back into GCP."""
    envelope = _envelope(dispatcher)
    leaky = _result(envelope, output="found this key sk-proj-AAAABBBBCCCCDDDDEEEEFFFF")
    verification = dispatcher.verify_worker_result(envelope, leaky)
    assert not verification.accepted
    assert verification.status.value == "BLOCKED"
    assert any("secret-shaped" in r for r in verification.reasons)


def test_worker_reporting_failure_does_not_become_done(dispatcher):
    envelope = _envelope(dispatcher)
    failed = _result(envelope, status="BLOCKED")
    verification = dispatcher.verify_worker_result(envelope, failed)
    assert not verification.accepted
    assert verification.status.value != "DONE"


# ── §19 failure rules ───────────────────────────────────────────────────

def test_worker_fails_closed_without_the_control_plane():
    should_stop, reason = worker_should_fail_closed(control_plane_reachable=False)
    assert should_stop
    for forbidden in ("publishing", "trading", "production merge", "governance mutation"):
        assert forbidden in reason


def test_worker_operates_normally_with_the_control_plane():
    should_stop, _ = worker_should_fail_closed(control_plane_reachable=True)
    assert not should_stop


def test_gcp_survives_total_oracle_loss(registry, dispatcher):
    """Every Oracle worker gone: primary work continues, Oracle work blocks."""
    for worker in registry.by_cloud(Cloud.ORACLE):
        registry.mark_unreachable(worker.worker_id)

    assert dispatcher.select_worker("summarize", Sensitivity.PUBLIC) == "gcp-local-01"
    with pytest.raises(DispatchRefused):
        dispatcher.select_worker("draft_content", Sensitivity.PUBLIC)
