"""Independent-review regressions for PR #235."""
from __future__ import annotations

import importlib.util
import multiprocessing
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from core.authorization import AuthorizationLedger
from core.operator import BuddyOperator
import core.operator as operator_module
from core.learning_engine import _safe

CAP = "external.publish"
INSTRUCTION = "publish approved artifact"
DEST = "https://example.invalid/approved"


def _redeem_worker(state_dir, approval_id, start, out):
    ledger = AuthorizationLedger(Path(state_dir))
    start.wait()
    out.put(ledger.verify_and_consume(
        approval_id, capability=CAP, instruction=INSTRUCTION,
        content={"body": "approved"}, destination=DEST,
    ))


class AuthorizationConcurrencyTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "fork-based race regression")
    def test_grant_is_consumed_by_exactly_one_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = AuthorizationLedger(Path(tmp))
            req = ledger.request(
                mission_id="race", step=1, capability=CAP, instruction=INSTRUCTION,
                content={"body": "approved"}, destination=DEST,
            )
            self.assertTrue(ledger.grant(req["approval_id"])["ok"])
            ctx = multiprocessing.get_context("fork")
            start, out = ctx.Event(), ctx.Queue()
            workers = [ctx.Process(target=_redeem_worker,
                                   args=(tmp, req["approval_id"], start, out))
                       for _ in range(8)]
            for worker in workers:
                worker.start()
            start.set()
            for worker in workers:
                worker.join(10)
                self.assertEqual(worker.exitcode, 0)
            rows = [out.get(timeout=2) for _ in workers]
            self.assertEqual(sum(bool(row.get("ok")) for row in rows), 1)
            self.assertEqual(sum(row.get("error") == "already_consumed" for row in rows), 7)


class OperatorAuthorityTests(unittest.TestCase):
    def _operator(self, tmp, delivered):
        operator = BuddyOperator(state_dir=Path(tmp))
        operator._external_executors["external:publish"] = delivered
        return operator

    def _plan(self, authorization_id=None):
        step = {"capability": "external.publish", "instruction": INSTRUCTION,
                "content": {"body": "approved"}, "destination": DEST}
        if authorization_id is not None:
            step["authorization_id"] = authorization_id
        return {"mission_id": "mission_reviewproof", "objective": "publish",
                "kind": "external_publish", "evidence_policy": None,
                "created_at": "2026-09-04T00:00:00+00:00", "steps": [step]}

    def test_malformed_authorization_returns_blocked_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            op = self._operator(tmp, lambda step, ctx: {"delivered": False})
            result = op.execute(self._plan("../approval"))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["receipts"][0]["errors"][0]["error"], "AuthorizationRejected")

    def test_grant_and_resume_uses_stored_exact_payload(self):
        delivered = []

        def backend(step, context):
            delivered.append((step.get("content"), step.get("destination")))
            return {
                "delivered": True,
                "result": {"ok": True},
                "evidence": [{
                    "receipt_id": "r-1",
                    "platform": "example.invalid",
                    "observed_at": "2026-09-05T06:47:00Z",
                }],
            }

        with tempfile.TemporaryDirectory() as tmp:
            op = self._operator(tmp, backend)
            held = op.execute(self._plan())
            self.assertEqual(held["status"], "HELD")
            with mock.patch.object(
                operator_module,
                "governed_audit_log",
                return_value={"seq": 11, "hash": "b" * 64, "event": "external_action_executed"},
            ):
                result = op.grant_and_resume(held["held"]["approval_id"], session_id="test")
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(delivered, [({"body": "approved"}, DEST)])
            self.assertIn("authority_ref", result["receipts"][0])
            self.assertEqual(result["receipts"][0]["governed_audit"]["seq"], 11)

    def test_delivery_without_evidence_never_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            op = self._operator(tmp, lambda step, ctx: {"delivered": True, "result": "done"})
            held = op.execute(self._plan())
            result = op.grant_and_resume(held["held"]["approval_id"])
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["receipts"][0]["status"], "DELIVERED_UNVERIFIED")

    def test_post_delivery_audit_failure_is_truthful(self):
        with tempfile.TemporaryDirectory() as tmp:
            op = self._operator(tmp, lambda step, ctx: {
                "delivered": True,
                "result": "done",
                "evidence": [{
                    "receipt_id": "r-2",
                    "platform": "example.invalid",
                    "observed_at": "2026-09-05T06:48:00Z",
                }],
            })
            held = op.execute(self._plan())
            original = operator_module.governed_audit_log
            operator_module.governed_audit_log = (
                lambda *a, **k: (_ for _ in ()).throw(OSError("audit down"))
            )
            try:
                result = op.grant_and_resume(held["held"]["approval_id"])
            finally:
                operator_module.governed_audit_log = original
            self.assertEqual(result["receipts"][0]["status"], "DELIVERED_AUDIT_UNAVAILABLE")
            self.assertNotEqual(result["status"], "COMPLETE")

    def test_safe_authority_metadata_survives_redaction(self):
        clean = _safe({"authority_ref": {"approval_id": "approval_abc123abc123",
                                         "authorization_sequence": 7,
                                         "payload_hash": "deadbeef", "approver": "founder",
                                         "approval_hash": "secret-proof"}})
        self.assertEqual(clean["authority_ref"]["approval_id"], "approval_abc123abc123")
        self.assertEqual(clean["authority_ref"]["authorization_sequence"], 7)
        self.assertEqual(clean["authority_ref"]["approval_hash"], "[REDACTED]")


class StaticGovernanceTests(unittest.TestCase):
    def test_external_binding_validator_ignores_comments(self):
        path = ROOT / "scripts" / "validate_elite_governance.py"
        spec = importlib.util.spec_from_file_location("elite_review", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.external_executor_bindings('# self._external_executors={"external:publish": 1}'), set())
        self.assertEqual(mod.external_executor_bindings('self._external_executors={"external:publish": self.x}'), {"external:publish"})

    def test_product_surfaces_have_explicit_authenticated_resume(self):
        web = (ROOT / "buddy_core" / "buddy_web.py").read_text(encoding="utf-8")
        bridge = (ROOT / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
        self.assertIn('body.get("approve") is True', web)
        self.assertIn("grant_and_resume", web)
        self.assertIn('data.get("approve") is True', bridge)
        self.assertIn("grant_and_resume", bridge)

    def test_temporary_applicators_are_removed(self):
        self.assertFalse(list((ROOT / ".github" / "workflows").glob("pr235-review-fix*.yml")))


if __name__ == "__main__":
    unittest.main()
