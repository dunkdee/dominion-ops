from __future__ import annotations

from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    value = read(path)
    count = value.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:140]!r}")
    write(path, value.replace(old, new, 1))


# ---------------------------------------------------------------------------
# 1. Consequential external delivery: meaningful receipt + tamper-evident audit
# ---------------------------------------------------------------------------
path = "buddy_core/core/operator.py"
source = read(path)

if "governed_audit_log" not in source:
    anchor = "from buddy_core.core.authorization import AuthorizationError, AuthorizationLedger, payload_fingerprint\n"
    if anchor not in source:
        raise SystemExit("operator authorization import anchor missing")
    source = source.replace(
        anchor,
        anchor
        + "\ntry:\n"
        + "    from watchmen.saraqael import log as governed_audit_log\n"
        + "except ImportError:  # repository/package execution used by CI/tests\n"
        + "    from buddy_core.watchmen.saraqael import log as governed_audit_log\n",
        1,
    )

method_match = re.search(
    r"\n    def _execute_external\(self, index: int, step: dict, cap: dict, context: dict,\n\s+authorization: dict\) -> dict:\n",
    source,
)
if not method_match:
    raise SystemExit("operator external method signature not found")

helper = '''
    @staticmethod
    def _validate_delivery_evidence(capability: str, evidence: Any) -> tuple[bool, str | None]:
        """Require a real capability-specific delivery receipt.

        A truthy dictionary, URL, or error object is not evidence of delivery.
        At least one item must contain a recognized receipt identifier,
        source/platform provenance, and an observation timestamp.
        """
        if not isinstance(evidence, list) or not evidence:
            return False, None

        receipt_keys = {
            "external.publish": ("platform_receipt_id", "publication_id", "post_id", "receipt_id"),
            "external.message": ("send_receipt_id", "message_id", "receipt_id"),
            "external.spend": ("financial_receipt_id", "transaction_id", "payment_id", "receipt_id"),
        }.get(capability, ("receipt_id",))
        provenance_keys = ("platform", "provider", "system", "source")
        time_keys = ("observed_at", "delivered_at", "timestamp", "created_at")

        for item in evidence:
            if not isinstance(item, dict) or not item:
                continue
            receipt_id = next(
                (str(item.get(key)).strip() for key in receipt_keys if str(item.get(key) or "").strip()),
                None,
            )
            provenance = next(
                (str(item.get(key)).strip() for key in provenance_keys if str(item.get(key) or "").strip()),
                None,
            )
            observed_at = next(
                (str(item.get(key)).strip() for key in time_keys if str(item.get(key) or "").strip()),
                None,
            )
            if receipt_id and provenance and observed_at:
                return True, receipt_id
        return False, None
'''
source = source[: method_match.start()] + "\n" + helper + source[method_match.start() :]

method_start = source.index("    def _execute_external(")
next_method = source.index("\n    def _no_delivery_backend", method_start)
method = source[method_start:next_method]
evidence_start = method.index('        evidence = outcome.get("evidence")')
prefix = method[:evidence_start]
replacement_tail = '''        evidence = outcome.get("evidence")
        evidence_ok, receipt_id = self._validate_delivery_evidence(
            step["capability"], evidence
        )
        if not evidence_ok:
            return {**base, "status": "DELIVERED_UNVERIFIED",
                    "errors": [{"attempt": 1, "error": "DeliveryEvidenceMissing",
                                "detail": "delivery occurred but no capability-specific receipt with provenance and timestamp was present"}],
                    "result": outcome.get("result"),
                    "evidence": evidence if isinstance(evidence, list) else []}

        evidence_hash = hashlib.sha256(
            json.dumps(
                evidence,
                sort_keys=True,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        try:
            governed_entry = governed_audit_log(
                "buddy_operator",
                "external_action_executed",
                "ok",
                {
                    "capability": step["capability"],
                    "approval_id": authorization.get("approval_id"),
                    "destination": step.get("destination"),
                    "payload_hash": authorization.get("payload_hash"),
                    "delivery_receipt_id": receipt_id,
                    "delivery_evidence_sha256": evidence_hash,
                },
            )
        except Exception as exc:
            return {**base, "status": "DELIVERED_AUDIT_UNAVAILABLE",
                    "errors": [{"attempt": 1, "error": "PostDeliveryAuditUnavailable",
                                "detail": type(exc).__name__}],
                    "result": outcome.get("result"), "evidence": evidence}

        return {**base, "status": "VERIFIED", "errors": [],
                "result": outcome.get("result"), "evidence": evidence,
                "governed_audit": {
                    "seq": governed_entry.get("seq"),
                    "hash": governed_entry.get("hash"),
                    "event": governed_entry.get("event"),
                }}
'''
source = source[:method_start] + prefix + replacement_tail + source[next_method:]
write(path, source)


# ---------------------------------------------------------------------------
# 2. Rollback: never clean/apply backed-up state if switching to PREVIOUS_SHA fails
# ---------------------------------------------------------------------------
path = "scripts/deploy_foundation_vm_remote.sh"
old = '''  set +e
  # Move HEAD and worktree back to the previous release. `switch --detach`
  # without --force refuses on unexpected drift instead of destroying it,
  # which is the fail-closed behaviour governance requires.
  git switch --detach --quiet "$PREVIOUS_SHA"
  git clean -fdq

  if [ -s "$LOCAL_STATE_BACKUP/index.patch" ]; then
    git apply --index --binary --whitespace=nowarn "$LOCAL_STATE_BACKUP/index.patch"
    rc=$?
  fi
'''
new = '''  set +e
  # A failed switch is terminal for restore: never clean/apply state on an
  # unknown commit.
  restore_output="$(git switch --detach --quiet "$PREVIOUS_SHA" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    clean_output="$(git clean -fdq 2>&1)"
    rc=$?
    if [ -n "$clean_output" ]; then
      restore_output="${restore_output};${clean_output}"
    fi
  fi

  if [ "$rc" -eq 0 ] && [ -s "$LOCAL_STATE_BACKUP/index.patch" ]; then
    restore_output="$(git apply --index --binary --whitespace=nowarn "$LOCAL_STATE_BACKUP/index.patch" 2>&1)"
    rc=$?
  fi
'''
replace_once(path, old, new)


# ---------------------------------------------------------------------------
# 3. Regressions for exact reviewer findings
# ---------------------------------------------------------------------------
path = "tests/test_buddy_authority_execution.py"
source = read(path)
if "from unittest import mock" not in source:
    source = source.replace("import unittest\n", "import unittest\nfrom unittest import mock\n", 1)

old_evidence = '''            return {"delivered": True,
                    "result": {"posted": True, "url": "https://example.invalid/p/1"},
                    "evidence": [{"url": "https://example.invalid/p/1"}]}
'''
new_evidence = '''            return {"delivered": True,
                    "result": {"posted": True, "url": "https://example.invalid/p/1"},
                    "evidence": [{
                        "platform_receipt_id": "post_123",
                        "platform": "example.invalid",
                        "observed_at": "2026-09-05T06:45:00Z",
                        "url": "https://example.invalid/p/1",
                    }]}
'''
if source.count(old_evidence) != 1:
    raise SystemExit(f"valid delivery fixture match count={source.count(old_evidence)}")
source = source.replace(old_evidence, new_evidence, 1)

old_assert = '''        record = self.run_plan(authorization_id=held["approval_id"])
        self.assertEqual(record["status"], "COMPLETE")
        receipt = self.last(record)
        self.assertEqual(receipt["status"], "VERIFIED")
        self.assertTrue(receipt["result"]["posted"])
'''
new_assert = '''        with mock.patch(
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
'''
if source.count(old_assert) != 1:
    raise SystemExit(f"valid delivery assertion match count={source.count(old_assert)}")
source = source.replace(old_assert, new_assert, 1)

anchor = "    def test_every_declared_external_capability_has_a_bound_executor(self):\n"
if anchor not in source:
    raise SystemExit("authority regression insertion anchor missing")
added = '''    def test_error_only_evidence_is_not_a_delivery_receipt(self):
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

'''
source = source.replace(anchor, added + anchor, 1)
write(path, source)

regression = r'''"""Final independent-review blocker regressions for PR #235."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FinalReviewBlockerTests(unittest.TestCase):
    def test_bridge_bearer_authorization_is_real_token_validation(self):
        source = (ROOT / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
        self.assertIn('expected = f"Bearer {BUDDY_WEB_TOKEN}"', source)
        self.assertIn("hmac.compare_digest(auth, expected)", source)
        self.assertNotIn('Authorization: ******', source)

    def test_rollback_gates_clean_and_patch_on_successful_switch(self):
        source = (ROOT / "scripts" / "deploy_foundation_vm_remote.sh").read_text(encoding="utf-8")
        restore = source.split("restore_local_state()", 1)[1].split("quarantine_local_state()", 1)[0]
        self.assertIn('restore_output="$(git switch --detach --quiet "$PREVIOUS_SHA" 2>&1)"', restore)
        self.assertIn('if [ "$rc" -eq 0 ]; then', restore)
        self.assertIn('if [ "$rc" -eq 0 ] && [ -s "$LOCAL_STATE_BACKUP/index.patch" ]', restore)

    def test_external_delivery_uses_tamper_evident_audit(self):
        source = (ROOT / "buddy_core" / "core" / "operator.py").read_text(encoding="utf-8")
        external = source.split("def _execute_external", 1)[1].split("def _no_delivery_backend", 1)[0]
        self.assertIn("governed_audit_log(", external)
        self.assertIn("delivery_evidence_sha256", external)
        self.assertNotIn('audit("external_action_executed"', external)

    def test_external_delivery_requires_receipt_provenance_and_time(self):
        source = (ROOT / "buddy_core" / "core" / "operator.py").read_text(encoding="utf-8")
        self.assertIn("platform_receipt_id", source)
        self.assertIn("provenance_keys", source)
        self.assertIn("time_keys", source)


if __name__ == "__main__":
    unittest.main()
'''
(ROOT / "tests" / "test_pr235_final_review_blockers.py").write_text(
    textwrap.dedent(regression), encoding="utf-8"
)

# Remove all temporary applicators from the final candidate tree.
for helper in (
    ".github/workflows/pr235-final-blocker-fix-v14.yml",
    ".github/workflows/pr235-final-blocker-fix-v15.yml",
    ".github/workflows/pr235-final-blocker-fix-v16.yml",
    ".github/scripts/pr235_final_fix.py",
):
    hp = ROOT / helper
    if hp.exists():
        hp.unlink()

print("PR235_FINAL_BLOCKERS_PATCHED")
