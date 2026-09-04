"""Founder authorization ledger — the key to the external boundary.

These tests are written adversarially on purpose. This module is the only
thing standing between a prepared mission and a real external effect, so the
failure modes that matter are replay, payload swap, tampering, and expiry.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "buddy_core"))

from core.authorization import (  # noqa: E402
    CONSUMED,
    DENIED,
    GRANTED,
    PENDING,
    AuthorizationError,
    AuthorizationLedger,
    payload_fingerprint,
)

CAP = "external.publish"
INSTRUCTION = "publish the traffic package"
CONTENT = {"title": "Divine Sovereignty", "body": "the approved words"}
DEST = "youtube:dominion-channel"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger = AuthorizationLedger(Path(self._tmp.name))

    def make(self, **over):
        kwargs = dict(mission_id="m1", step=5, capability=CAP,
                      instruction=INSTRUCTION, content=CONTENT, destination=DEST)
        kwargs.update(over)
        return self.ledger.request(**kwargs)

    def consume(self, approval_id, **over):
        kwargs = dict(capability=CAP, instruction=INSTRUCTION,
                      content=CONTENT, destination=DEST)
        kwargs.update(over)
        return self.ledger.verify_and_consume(approval_id, **kwargs)

    # ── the happy path exists at all ─────────────────────────────────────

    def test_request_grant_consume_is_the_only_path_to_execution(self):
        req = self.make()
        self.assertEqual(req["status"], PENDING)
        self.assertIsNone(req["authorization_sequence"])

        granted = self.ledger.grant(req["approval_id"])
        self.assertTrue(granted["ok"])
        self.assertEqual(granted["authorization"]["status"], GRANTED)
        self.assertEqual(granted["authorization"]["approver"], "founder")

        used = self.consume(req["approval_id"])
        self.assertTrue(used["ok"])
        self.assertEqual(used["authorization"]["status"], CONSUMED)

    def test_pending_lists_what_awaits_the_founder(self):
        a = self.make()
        b = self.make(mission_id="m2")
        ids = {r["approval_id"] for r in self.ledger.pending()}
        self.assertEqual(ids, {a["approval_id"], b["approval_id"]})

        self.ledger.grant(a["approval_id"])
        self.assertEqual([r["approval_id"] for r in self.ledger.pending()], [b["approval_id"]])

    def test_preview_shows_the_founder_what_is_being_published(self):
        req = self.make(content="the exact words that will go out")
        self.assertIn("the exact words", req["content_preview"])

    # ── ungranted work never executes ────────────────────────────────────

    def test_pending_authorization_cannot_be_consumed(self):
        req = self.make()
        self.assertEqual(self.consume(req["approval_id"])["error"], "not_granted")

    def test_denied_authorization_cannot_be_consumed_or_granted(self):
        req = self.make()
        self.ledger.deny(req["approval_id"], reason="off brand")
        self.assertEqual(self.consume(req["approval_id"])["error"], "not_granted")
        self.assertEqual(self.ledger.grant(req["approval_id"])["error"], "already_denied")

    def test_unknown_approval_id_is_refused(self):
        self.assertEqual(self.consume("approval_deadbeefcafe")["error"], "unknown_approval_id")
        self.assertEqual(self.ledger.grant("approval_deadbeefcafe")["error"], "unknown_approval_id")

    # ── replay ───────────────────────────────────────────────────────────

    def test_authorization_is_single_use(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.assertTrue(self.consume(req["approval_id"])["ok"])
        second = self.consume(req["approval_id"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"], "already_consumed")

    def test_consumed_authorization_cannot_be_re_granted(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.consume(req["approval_id"])
        self.assertEqual(self.ledger.grant(req["approval_id"])["error"], "already_consumed")

    def test_double_grant_is_refused(self):
        req = self.make()
        self.assertTrue(self.ledger.grant(req["approval_id"])["ok"])
        self.assertEqual(self.ledger.grant(req["approval_id"])["error"], "already_granted")

    # ── the approval cannot be redirected ────────────────────────────────

    def test_approval_cannot_be_redirected_to_different_content(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        swapped = self.consume(req["approval_id"], content={"body": "something else entirely"})
        self.assertFalse(swapped["ok"])
        self.assertEqual(swapped["error"], "payload_mismatch")

    def test_approval_cannot_be_redirected_to_a_different_destination(self):
        # Approving a post to one place must never authorize the same words
        # somewhere else.
        req = self.make()
        self.ledger.grant(req["approval_id"])
        swapped = self.consume(req["approval_id"], destination="tiktok:other-account")
        self.assertEqual(swapped["error"], "payload_mismatch")

    def test_approval_cannot_be_redirected_to_a_different_capability(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.assertEqual(self.consume(req["approval_id"], capability="external.message")["error"],
                         "payload_mismatch")

    def test_a_failed_payload_match_does_not_burn_the_authorization(self):
        # A mismatch is refused, but the Founder's genuine approval survives
        # so the correct payload can still go out.
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.assertEqual(self.consume(req["approval_id"], content="wrong")["error"], "payload_mismatch")
        self.assertTrue(self.consume(req["approval_id"])["ok"])

    def test_fingerprint_is_stable_and_destination_sensitive(self):
        a = payload_fingerprint(CAP, INSTRUCTION, CONTENT, DEST)
        self.assertEqual(a, payload_fingerprint(CAP, INSTRUCTION, CONTENT, DEST))
        self.assertNotEqual(a, payload_fingerprint(CAP, INSTRUCTION, CONTENT, "elsewhere"))

    # ── tampering ────────────────────────────────────────────────────────

    def test_tampered_record_is_detected_on_consume(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        path = self.ledger.root / f"{req['approval_id']}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["payload_hash"] = payload_fingerprint(CAP, INSTRUCTION, "hijacked", DEST)
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.consume(req["approval_id"], content="hijacked")["error"],
                         "authorization_record_tampered")

    def test_status_cannot_be_hand_edited_to_granted(self):
        req = self.make()
        path = self.ledger.root / f"{req['approval_id']}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["status"] = GRANTED
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.consume(req["approval_id"])["error"],
                         "authorization_record_tampered")

    # ── expiry and sequence ──────────────────────────────────────────────

    def test_expired_request_cannot_be_granted(self):
        req = self.make(ttl_seconds=-1)
        self.assertEqual(self.ledger.grant(req["approval_id"])["error"], "expired")

    def test_expired_grant_cannot_be_consumed(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        path = self.ledger.root / f"{req['approval_id']}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        stale = datetime.now(timezone.utc) - timedelta(hours=1)
        record["expires_at"] = stale.isoformat()
        # Re-seal so this tests expiry, not tampering.
        from core.authorization import _hash_without
        record["approval_hash"] = _hash_without(record, "approval_hash")
        path.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.consume(req["approval_id"])["error"], "expired")

    def test_expired_requests_drop_out_of_the_pending_list(self):
        self.make(ttl_seconds=-1)
        self.assertEqual(self.ledger.pending(), [])

    def test_grants_take_a_monotonic_sequence(self):
        seqs = []
        for i in range(3):
            req = self.make(mission_id=f"m{i}")
            seqs.append(self.ledger.grant(req["approval_id"])["authorization"]["authorization_sequence"])
        self.assertEqual(seqs, [1, 2, 3])

    def test_sequence_survives_a_new_ledger_instance(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        reopened = AuthorizationLedger(Path(self._tmp.name))
        second = reopened.grant(self.make(mission_id="m2")["approval_id"])
        self.assertEqual(second["authorization"]["authorization_sequence"], 2)

    # ── durability and hygiene ───────────────────────────────────────────

    def test_authorizations_persist_across_instances(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        reopened = AuthorizationLedger(Path(self._tmp.name))
        self.assertTrue(reopened.verify_and_consume(
            req["approval_id"], capability=CAP, instruction=INSTRUCTION,
            content=CONTENT, destination=DEST)["ok"])

    def test_every_decision_leaves_a_receipt(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.consume(req["approval_id"])
        events = [json.loads(line)["event"]
                  for line in self.ledger.receipts_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events, ["authorization_requested", "authorization_granted",
                                  "authorization_consumed"])

    def test_replay_and_mismatch_attempts_are_recorded(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.consume(req["approval_id"], content="wrong")
        self.consume(req["approval_id"])
        self.consume(req["approval_id"])
        body = self.ledger.receipts_path.read_text(encoding="utf-8")
        self.assertIn("payload_mismatch", body)
        self.assertIn("replay", body)

    def test_traversal_in_approval_id_is_refused(self):
        for bad in ("../escape", "a/b", "..", ".hidden"):
            with self.assertRaises(AuthorizationError):
                self.ledger.load(bad)

    def test_records_are_not_world_readable(self):
        req = self.make()
        mode = (self.ledger.root / f"{req['approval_id']}.json").stat().st_mode
        self.assertEqual(mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
