from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "buddy_core"))

from core.authorization import (  # noqa: E402
    AuthorizationLedger,
    CONSUMED,
    DENIED,
    GRANTED,
    PENDING,
    payload_fingerprint,
)

CAP = "external.publish"
INSTRUCTION = "publish governed content"
CONTENT = "hello"
DEST = "channel://dominion"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_key = os.environ.get("DOMINION_AUTHORIZATION_HMAC_KEY")
        os.environ["DOMINION_AUTHORIZATION_HMAC_KEY"] = "a" * 64
        self.ledger = AuthorizationLedger(Path(self._tmp.name))

    def tearDown(self):
        if self._old_key is None:
            os.environ.pop("DOMINION_AUTHORIZATION_HMAC_KEY", None)
        else:
            os.environ["DOMINION_AUTHORIZATION_HMAC_KEY"] = self._old_key
        self._tmp.cleanup()

    def make(self, **kw):
        return self.ledger.request(
            mission_id=kw.pop("mission_id", "m1"),
            capability=kw.pop("capability", CAP),
            instruction=kw.pop("instruction", INSTRUCTION),
            content=kw.pop("content", CONTENT),
            destination=kw.pop("destination", DEST),
            **kw,
        )

    def consume(self, approval_id, **kw):
        return self.ledger.consume(
            approval_id,
            mission_id=kw.pop("mission_id", "m1"),
            capability=kw.pop("capability", CAP),
            instruction=kw.pop("instruction", INSTRUCTION),
            content=kw.pop("content", CONTENT),
            destination=kw.pop("destination", DEST),
            **kw,
        )

    # ── happy path ───────────────────────────────────────────────────────

    def test_request_starts_pending_and_grant_makes_it_consumable(self):
        req = self.make()
        self.assertTrue(req["ok"])
        self.assertEqual(req["authorization"]["status"], PENDING)
        grant = self.ledger.grant(req["approval_id"])
        self.assertTrue(grant["ok"])
        self.assertEqual(grant["authorization"]["status"], GRANTED)
        consumed = self.consume(req["approval_id"])
        self.assertTrue(consumed["ok"])
        self.assertEqual(consumed["authorization"]["status"], CONSUMED)

    def test_pending_lists_only_live_pending_requests(self):
        a = self.make(mission_id="a")
        b = self.make(mission_id="b")
        self.ledger.grant(b["approval_id"])
        pending = self.ledger.pending()
        self.assertEqual([r["approval_id"] for r in pending], [a["approval_id"]])

    def test_deny_blocks_consumption(self):
        req = self.make()
        denied = self.ledger.deny(req["approval_id"], reason="no")
        self.assertTrue(denied["ok"])
        self.assertEqual(denied["authorization"]["status"], DENIED)
        self.assertEqual(self.consume(req["approval_id"])["error"], "denied")

    # ── binding / substitution ──────────────────────────────────────────

    def test_payload_is_bound_to_mission_capability_instruction_content_and_destination(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        variants = [
            {"mission_id": "other"},
            {"capability": "external.message"},
            {"instruction": "different"},
            {"content": "different"},
            {"destination": "other"},
        ]
        for change in variants:
            with self.subTest(change=change):
                result = self.consume(req["approval_id"], **change)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "authorization_payload_mismatch")

    def test_grant_does_not_change_payload_hash(self):
        req = self.make()
        before = req["authorization"]["payload_hash"]
        after = self.ledger.grant(req["approval_id"])["authorization"]
        self.assertEqual(before, after["payload_hash"])

    # ── single use / replay ─────────────────────────────────────────────

    def test_authorization_is_single_use(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.assertTrue(self.consume(req["approval_id"])["ok"])
        replay = self.consume(req["approval_id"])
        self.assertFalse(replay["ok"])
        self.assertEqual(replay["error"], "authorization_already_consumed")

    def test_different_approval_id_cannot_consume_another_request(self):
        a = self.make(mission_id="a")
        b = self.make(mission_id="b")
        self.ledger.grant(a["approval_id"])
        result = self.consume(b["approval_id"], mission_id="a")
        self.assertFalse(result["ok"])

    # ── tamper evidence ─────────────────────────────────────────────────

    def test_payload_tamper_is_detected(self):
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
        # Re-seal with the ledger's keyed MAC so this tests expiry, not tampering.
        record["approval_hash"] = self.ledger._record_mac(record)
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

    def test_atomic_write_does_not_leave_temp_files(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        leftovers = [p for p in self.ledger.root.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_receipt_is_written_on_consume(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        self.consume(req["approval_id"])
        lines = self.ledger.receipts_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        receipt = json.loads(lines[0])
        self.assertEqual(receipt["approval_id"], req["approval_id"])
        self.assertEqual(receipt["status"], CONSUMED)

    def test_new_ledger_same_key_can_verify_existing_records(self):
        req = self.make()
        self.ledger.grant(req["approval_id"])
        reopened = AuthorizationLedger(Path(self._tmp.name))
        self.assertEqual(reopened.load(req["approval_id"])["status"], GRANTED)
        self.assertTrue(reopened.consume(
            req["approval_id"],
            mission_id="m1",
            capability=CAP,
            instruction=INSTRUCTION,
            content=CONTENT,
            destination=DEST,
        )["ok"])


if __name__ == "__main__":
    unittest.main()
