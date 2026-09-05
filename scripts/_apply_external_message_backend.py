from pathlib import Path
import re

operator_path = Path("buddy_core/core/operator.py")
text = operator_path.read_text(encoding="utf-8")

freeze_lines = [
    "    def _freeze_external_step(self, step: dict, context: dict) -> dict:",
    "        \"\"\"Bind authority to the exact content/destination the executor will receive.\"\"\"",
    "        if step.get(\"capability\") == \"external.message\":",
    "            try:",
    "                from core.message_delivery import freeze_authorized_email_step",
    "            except ImportError:",
    "                from buddy_core.core.message_delivery import freeze_authorized_email_step",
    "            return freeze_authorized_email_step(",
    "                copy.deepcopy(step),",
    "                list(context.get(\"outputs\", [])),",
    "                self.staged_dir,",
    "            )",
    "        frozen = copy.deepcopy(step)",
    "        if \"content\" not in frozen or frozen.get(\"content\") is None:",
    "            outputs = [value for value in context.get(\"outputs\", []) if value is not None]",
    "            frozen[\"content\"] = copy.deepcopy(outputs[-1]) if outputs else None",
    "        # Destination may legitimately be None, but no later executor may invent one.",
    "        frozen[\"destination\"] = step.get(\"destination\")",
    "        return frozen",
    "",
]
text, count = re.subn(
    r"    def _freeze_external_step\(self, step: dict, context: dict\) -> dict:\n.*?(?=    def _held_path\()",
    "\n".join(freeze_lines),
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("freeze method structural match failed")

old = (
    "                frozen_step = self._freeze_external_step(step, context)\n"
    "                destination = frozen_step.get(\"destination\")\n"
    "                supplied = frozen_step.get(\"authorization_id\")\n"
)
prep_lines = [
    "                try:",
    "                    frozen_step = self._freeze_external_step(step, context)",
    "                except (OperatorError, TypeError, ValueError) as exc:",
    "                    receipts.append({",
    "                        \"step\": index,",
    "                        \"capability\": step[\"capability\"],",
    "                        \"status\": \"BLOCKED\",",
    "                        \"attempts\": 0,",
    "                        \"errors\": [{",
    "                            \"attempt\": 0,",
    "                            \"error\": \"ExternalPayloadPreparationError\",",
    "                            \"detail\": str(exc)[:200],",
    "                        }],",
    "                        \"result\": None,",
    "                        \"evidence\": [],",
    "                    })",
    "                    break",
    "                destination = frozen_step.get(\"destination\")",
    "                supplied = frozen_step.get(\"authorization_id\")",
    "",
]
if text.count(old) != 1:
    raise SystemExit("execution preparation exact match failed")
text = text.replace(old, "\n".join(prep_lines), 1)

message_lines = [
    "    def _external_message(self, step: dict, context: dict) -> dict:",
    "        # `_execute_external` passes only the authorization-fingerprinted shape.",
    "        # Ambient/regenerated mission context is intentionally ignored here.",
    "        try:",
    "            from core.message_delivery import deliver_authorized_email",
    "        except ImportError:",
    "            from buddy_core.core.message_delivery import deliver_authorized_email",
    "        return deliver_authorized_email(step)",
    "",
]
text, count = re.subn(
    r"    def _external_message\(self, step: dict, context: dict\) -> dict:\n.*?(?=    def _external_spend\()",
    "\n".join(message_lines),
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("external.message method structural match failed")
operator_path.write_text(text, encoding="utf-8")

delivery_path = Path("buddy_core/core/message_delivery.py")
delivery = delivery_path.read_text(encoding="utf-8")
marker = (
    "    supplied = frozen.get(\"content\")\n"
    "    if supplied is None:\n"
    "        candidates = [value for value in outputs if value is not None]\n"
    "        supplied = candidates[-1] if candidates else None\n"
    "    raw = _artifact_text(supplied, staged_root)\n"
    "    subject, body = _subject_and_body(raw)\n"
)
structured_lines = [
    "    supplied = frozen.get(\"content\")",
    "    if supplied is None:",
    "        candidates = [value for value in outputs if value is not None]",
    "        supplied = candidates[-1] if candidates else None",
    "",
    "    # A resumed held plan already contains the canonical envelope. Preserve",
    "    # it byte-for-byte so replay executes the exact payload Founder granted.",
    "    if isinstance(supplied, dict):",
    "        existing_subject = str(supplied.get(\"subject\") or \"\").strip()",
    "        existing_body = str(supplied.get(\"body_text\") or \"\")",
    "        existing_hash = str(supplied.get(\"content_sha256\") or \"\").strip().lower()",
    "        if existing_subject and existing_body:",
    "            actual = _sha256_text(existing_subject + \"\\n\" + existing_body)",
    "            if existing_hash != actual:",
    "                raise ValueError(\"external.message frozen content hash mismatch\")",
    "            if len(existing_subject) > _MAX_SUBJECT or len(existing_body.encode(\"utf-8\")) > _MAX_BODY_BYTES:",
    "                raise ValueError(\"external.message frozen content exceeds bounded size\")",
    "            frozen[\"destination\"] = destination",
    "            frozen[\"content\"] = {",
    "                \"subject\": existing_subject,",
    "                \"body_text\": existing_body,",
    "                \"content_sha256\": existing_hash,",
    "            }",
    "            return frozen",
    "",
    "    raw = _artifact_text(supplied, staged_root)",
    "    subject, body = _subject_and_body(raw)",
    "",
]
if delivery.count(marker) != 1:
    raise SystemExit("message resume marker exact match failed")
delivery_path.write_text(delivery.replace(marker, "\n".join(structured_lines), 1), encoding="utf-8")

# Remove the temporary mutation mechanism from the candidate tree before policy tests.
Path(".github/workflows/apply-governed-external-message-backend.yml").unlink()
Path(__file__).unlink()
