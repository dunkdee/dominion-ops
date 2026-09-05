"""Governed external execution: authority is required, and never fabricated.

The operator holds every consequential capability, records a durable
authorization request, and only dispatches once that exact authority has been
redeemed. These tests exercise that path end to end through the real operator,
with the emphasis on the negative cases — because the failure that matters is
Buddy reporting an action it never performed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from core.authorization import AuthorizationLedger  # noqa: E402
from core.operator import BuddyOperator  # noqa: E402

CAP = "external.publish"
INSTRUCTION = "publish the approved traffic package"
CONTENT = {"body": "the approved words"}
DEST = "dominionhealing.org/r/voltedge-speaker-offer-v1"


def _plan(operator, **step_over):
    step = {"capability": CAP, "instruction": INSTRUCTION,
            "content": CONTENT, "destination": DEST}
    step.update(step_over)
    return {
        "mission_id": "mission_test_authority",
        "objective": "publish the package",
        "steps": [step],
        "evidence_policy": "HYBRID",
    }


class AuthorityExecutionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name)
        self.operator = BuddyOperator(state_dir=self.state)
        self.ledger = AuthorizationLedger(self.state)

    def run_plan(self, **step_over):
        return self.operator.execute(_plan(self.operator, **step_over),
                                     session_id="test")

    def last(self, record):
        return record["receipts"][-1]

    # ── holding ──────────────────────────────────────────────────────────

    def test_unauthorized_consequential_step_holds_and_records_a_request(self):
        record = self.run_plan()
        self.assertEqual(record["status"], "HELD")
        held = record["held"]
        self.assertEqual(held["capability"], CAP)
        self.assertIn("approval_id", held)
        # The hold is durable, not a throwaway identifier.
        stored = self.ledger.load(held["approval_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["status"], "PENDING")
        self.assertEqual(stored["payload_hash"], held["payload_hash"])

    def test_held_mission_performs_no_external_action(self):
        record = self.run_plan()
        statuses = {r["status"] for r in record["receipts"]}
        self.assertNotIn("VERIFIED", statuses)
        self.assertEqual(record["status"], "HELD")

    def test_hold_appears_in_the_pending_queue_for_the_founder(self):
        record = self.run_plan()
        pending = {r["approval_id"] for r in self.ledger.pending()}
        self.assertIn(record["held"]["approval_id"], pending)

    # ── negative authority ───────────────────────────────────────────────

    def test_unknown_authorization_is_blocked(self):
        record = self.run_plan(authorization_id="approval_does_not_exist")
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["detail"], "unknown_approval_id")

    def test_ungranted_authorization_is_blocked(self):
        held = self.run_plan()["held"]
        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["detail"], "not_granted")

    def test_expired_authorization_is_blocked(self):
        request = self.ledger.request(
            mission_id="m", step=1, capability=CAP, instruction=INSTRUCTION,
            content=CONTENT, destination=DEST, ttl_seconds=-1)
        record = self.run_plan(authorization_id=request["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")

    def test_authorization_for_different_content_is_blocked(self):
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"],
                               content={"body": "something the Founder never saw"})
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["detail"], "payload_mismatch")

    def test_authorization_for_different_destination_is_blocked(self):
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"],
                               destination="tiktok:some-other-account")
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["detail"], "payload_mismatch")

    def test_authorization_cannot_be_replayed(self):
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        first = self.run_plan(authorization_id=held["approval_id"])
        second = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(second["status"], "BLOCKED")
        self.assertEqual(self.last(second)["errors"][0]["detail"], "already_consumed")
        # The first attempt consumed the authority even though delivery was
        # unavailable, so a spent grant can never be reused.
        self.assertNotEqual(first["status"], "COMPLETE")

    # ── no fabricated execution ──────────────────────────────────────────

    def test_authorized_step_without_delivery_backend_is_blocked_not_completed(self):
        """The central guarantee: authority alone never becomes a claimed action."""
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        receipt = self.last(record)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertEqual(receipt["errors"][0]["error"], "ExternalDeliveryUnavailable")
        self.assertIsNone(receipt["result"])
        self.assertNotIn("VERIFIED", {r["status"] for r in record["receipts"]})

    def test_blocked_delivery_receipt_still_names_the_authority_used(self):
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        auth = self.last(record)["authorization"]
        self.assertEqual(auth["approval_id"], held["approval_id"])
        self.assertEqual(auth["approver"], "founder")
        self.assertIsInstance(auth["authorization_sequence"], int)

    def test_receipt_never_carries_authorization_secrets(self):
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        blob = repr(record)
        self.assertNotIn("approval_hash", blob)

    def test_executor_exception_produces_a_failure_receipt_never_success(self):
        def boom(step, context):
            raise RuntimeError("delivery backend exploded")

        self.operator._external_executors["external:publish"] = boom
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["error"], "RuntimeError")
        self.assertIsNone(self.last(record)["result"])

    def test_missing_executor_binding_is_blocked(self):
        self.operator._external_executors.pop("external:publish", None)
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["errors"][0]["error"], "ExecutorUnavailable")

    # ── the allowed path ─────────────────────────────────────────────────

    def test_delivering_executor_with_valid_authority_completes_with_evidence(self):
        delivered = {}

        def deliver(step, context):
            delivered["destination"] = step.get("destination")
            return {"delivered": True,
                    "result": {"posted": True, "url": "https://example.invalid/p/1"},
                    "evidence": [{
                        "platform_receipt_id": "post_123",
                        "platform": "example.invalid",
                        "observed_at": "2026-09-05T06:45:00Z",
                        "url": "https://example.invalid/p/1",
                    }]}

        self.operator._external_executors["external:publish"] = deliver
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        with mock.patch(
            "core.operator.governed_audit_log",
            return_value={"seq": 9, "hash": "a" * 64, "event": "external_action_executed"},
        ) as governed_audit:
            record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "COMPLETE")
        receipt = self.last(record)
        self.assertEqual(receipt["status"], "VERIFIED")
        self.assertTrue(receipt["result"]["posted"])
        self.assertEqual(receipt["governed_audit"]["seq"], 9)
        governed_audit.assert_called_once()
        self.assertEqual(delivered["destination"], DEST)
        # Authority is spent exactly once on a real delivery.
        self.assertEqual(self.ledger.load(held["approval_id"])["status"], "CONSUMED")

    def test_error_only_evidence_is_not_a_delivery_receipt(self):
        def deliver(step, context):
            return {
                "delivered": True,
                "result": {"posted": True},
                "evidence": [{"error": "receipt unavailable"}],
            }

        self.operator._external_executors["external:publish"] = deliver
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["status"], "DELIVERED_UNVERIFIED")

    def test_governed_audit_failure_blocks_verified_completion(self):
        def deliver(step, context):
            return {
                "delivered": True,
                "result": {"posted": True},
                "evidence": [{
                    "platform_receipt_id": "post_456",
                    "platform": "example.invalid",
                    "observed_at": "2026-09-05T06:46:00Z",
                }],
            }

        self.operator._external_executors["external:publish"] = deliver
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        with mock.patch("core.operator.governed_audit_log", side_effect=RuntimeError("audit down")):
            record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "BLOCKED")
        self.assertEqual(self.last(record)["status"], "DELIVERED_AUDIT_UNAVAILABLE")

    def test_executor_receives_only_authorization_bound_fields(self):
        """Un-fingerprinted step keys must never reach a real executor.

        payload_fingerprint() covers capability, instruction, content and
        destination only. Anything else on the persisted held plan passes
        redemption unchanged, so if it reached the executor an attacker who
        could write the held plan would steer a real delivery behind a valid
        Founder grant.
        """
        seen = {}

        def spy(step, context):
            seen["step"] = sorted(step.keys())
            seen["context"] = sorted(context.keys())
            seen["leaked"] = step.get("UNFINGERPRINTED_PAYLOAD")
            return {"delivered": False, "detail": "probe"}

        self.operator._external_executors["external:publish"] = spy
        held = self.run_plan()["held"]
        self.ledger.grant(held["approval_id"])
        self.run_plan(authorization_id=held["approval_id"],
                      UNFINGERPRINTED_PAYLOAD="attacker-controlled")
        authorized = ["capability", "content", "destination", "instruction"]
        self.assertEqual(seen["step"], authorized)
        self.assertEqual(seen["context"], authorized)
        self.assertIsNone(seen["leaked"])

    def test_every_declared_external_capability_has_a_bound_executor(self):
        for cap_id, cap in self.operator.capabilities.items():
            if not cap_id.startswith("external."):
                continue
            self.assertIn(cap.get("executor"), self.operator._external_executors,
                          f"{cap_id} declares an executor with no binding")


if __name__ == "__main__":
    unittest.main()
