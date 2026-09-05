"""Verify the deployed Buddy runtime and prove one governed external.message canary.

This runs ON the foundation VM against the deployed Buddy runtime. It proves the
whole path through Buddy's real authority boundary: exact deployed release,
plan, hold, Founder grant, exact frozen-payload redemption, SMTP acceptance,
governed audit, and single-use replay rejection.

It prints presence, identifiers and digests only. No secret value, and no
message body, is ever written to stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import traceback
import types
from pathlib import Path

SUBJECT = "Dominion Governed Delivery Canary"
BODY = ("This is a Founder-authorized Dominion production canary proving the "
        "governed external.message execution path. No action is required.")

out = []


def emit(key, value):
    line = f"CANARY_{key}={value}"
    out.append(line)
    print(line, flush=True)


def _load_env_file(path: Path, *, override: bool) -> bool:
    """Load one dotenv-style file with shell ordering semantics."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    loaded = False
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        try:
            parts = list(lexer)
        except ValueError:
            continue
        if not parts:
            value = ""
        elif len(parts) == 1:
            value = parts[0]
        else:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
        loaded = True
    return loaded


def _install_dotenv_shim() -> None:
    """Provide the minimal dotenv API this canary and Buddy runtime import."""
    module = types.ModuleType("dotenv")

    def load_dotenv(dotenv_path=None, override=False):
        candidate = Path(dotenv_path).expanduser() if dotenv_path else (Path.cwd() / ".env")
        return _load_env_file(candidate, override=bool(override))

    module.load_dotenv = load_dotenv
    sys.modules["dotenv"] = module


def load_runtime_env(home: Path):
    """Load the same dotenv files the Buddy runtime loads, first assignment wins."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        emit("DOTENV", "SHIM")
        _install_dotenv_shim()
        from dotenv import load_dotenv
    for candidate in (home / "buddy_core" / ".env", home / "conductor" / ".env", home / ".env"):
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_runtime_release(home: Path, expected_sha: str) -> bool:
    """Prove the copied Buddy runtime came from the exact successful deploy."""
    receipt_path = home / ".dominion" / "buddy" / "deployed_release.json"
    repo = home / "dominion-ops"
    runtime = home / "buddy_core"

    if not receipt_path.is_file():
        emit("DEPLOY_RECEIPT", "MISSING")
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        emit("DEPLOY_RECEIPT", "INVALID")
        return False
    if not isinstance(receipt, dict):
        emit("DEPLOY_RECEIPT", "INVALID")
        return False

    release_sha = str(receipt.get("release_sha") or "")
    emit("DEPLOY_RECEIPT", "PRESENT")
    emit("DEPLOYED_RELEASE_SHA", release_sha or "MISSING")
    release_matches = release_sha == expected_sha
    emit("DEPLOYED_RELEASE_SHA_MATCHES_EXPECTED", "YES" if release_matches else "NO")
    if not release_matches:
        return False

    recorded = receipt.get("files_sha256") or {}
    if not isinstance(recorded, dict) or not recorded:
        emit("DEPLOY_RECEIPT_FILE_HASHES", "MISSING")
        return False

    recorded_ok = True
    for rel, expected_hash in sorted(recorded.items()):
        path = runtime / str(rel)
        try:
            actual = _sha256_bytes(path.read_bytes())
        except OSError:
            actual = ""
        if actual != str(expected_hash):
            recorded_ok = False
            emit("DEPLOY_RECEIPT_FILE_HASH_MISMATCH", str(rel).replace("/", "_"))
    emit("DEPLOY_RECEIPT_FILE_HASHES", "MATCH" if recorded_ok else "MISMATCH")
    if not recorded_ok:
        return False

    critical = (
        "core/__init__.py",
        "core/operator.py",
        "core/authorization.py",
        "core/message_delivery.py",
        "watchmen/saraqael.py",
    )
    critical_ok = True
    for rel in critical:
        path = runtime / rel
        try:
            runtime_bytes = path.read_bytes()
            source_bytes = subprocess.run(
                ["git", "show", f"{expected_sha}:buddy_core/{rel}"],
                cwd=str(repo), capture_output=True, check=True,
            ).stdout
            matches = _sha256_bytes(runtime_bytes) == _sha256_bytes(source_bytes)
        except (OSError, subprocess.CalledProcessError):
            matches = False
        emit(f"RUNTIME_HASH_{rel.upper().replace('/', '_').replace('.', '_')}",
             "MATCH" if matches else "MISMATCH")
        critical_ok = critical_ok and matches

    emit("CRITICAL_RUNTIME_HASHES", "MATCH" if critical_ok else "MISMATCH")
    return critical_ok


def config_report(normalize_email) -> list[str]:
    """Resolve SMTP configuration with the executor's exact precedence."""
    missing: list[str] = []

    mode = os.getenv("BUDDY_EXTERNAL_MESSAGE_MODE", "hold").strip().lower()
    emit("CONFIG_MODE_IS_LIVE", "YES" if mode == "live" else f"NO({mode or 'unset'})")
    if mode != "live":
        missing.append("BUDDY_EXTERNAL_MESSAGE_MODE=live")

    host = os.getenv("SMTP_HOST", "mail.privateemail.com").strip()
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        port_ok = 1 <= port <= 65535
    except ValueError:
        port_ok = False
    emit("CONFIG_SMTP_HOST", "PRESENT" if host else "MISSING")
    emit("CONFIG_SMTP_PORT", "VALID" if port_ok else "INVALID")
    if not host:
        missing.append("SMTP_HOST")
    if not port_ok:
        missing.append("SMTP_PORT")

    username = os.getenv("SMTP_EMAIL", os.getenv("EMAIL_ADDRESS", "")).strip()
    password = os.getenv("SMTP_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
    from_email = normalize_email(
        os.getenv("BUDDY_MESSAGE_FROM_EMAIL", os.getenv("DRIP_FROM_EMAIL", username))
    )

    emit("CONFIG_SMTP_USERNAME", "PRESENT" if username else "MISSING")
    emit("CONFIG_SMTP_PASSWORD", "PRESENT" if password else "MISSING")
    emit("CONFIG_FROM_EMAIL", "VALID" if from_email else "INVALID")
    emit("CONFIG_SENDER_DOMAIN", from_email.rsplit("@", 1)[-1] if from_email else "UNRESOLVED")
    if not username:
        missing.append("SMTP_EMAIL/EMAIL_ADDRESS resolved value")
    if not password:
        missing.append("SMTP_PASSWORD/EMAIL_PASSWORD resolved value")
    if not from_email:
        missing.append("BUDDY_MESSAGE_FROM_EMAIL/DRIP_FROM_EMAIL resolved value")

    return missing


def stable_saraqael_snapshot(saraqael):
    """Verify and read one consistent audit snapshot under Saraqael's transaction lock."""
    with saraqael._exclusive_audit_lock():
        chain = saraqael.verify_chain()
        entries = saraqael._read_entries() if chain.get("valid") is True else []
    return chain, entries


def governed_audit_matches(entries: list[dict], audit: dict, evidence: list[dict], *,
                           approval_id: str, destination: str, payload_hash: str,
                           receipt_id: str) -> bool:
    """Bind the receipt audit pointer to the exact durable external-action entry."""
    try:
        seq = int(audit.get("seq"))
    except (TypeError, ValueError):
        return False
    audit_hash = str(audit.get("hash") or "")
    if seq < 1 or len(audit_hash) != 64 or audit.get("event") != "external_action_executed":
        return False

    entry = next((item for item in entries if isinstance(item, dict) and item.get("seq") == seq), None)
    if not entry or entry.get("hash") != audit_hash:
        return False
    details = entry.get("details") or {}
    if not isinstance(details, dict):
        return False

    try:
        evidence_blob = json.dumps(
            evidence,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        return False
    evidence_hash = hashlib.sha256(evidence_blob).hexdigest()

    return (
        entry.get("source") == "buddy_operator"
        and entry.get("event") == "external_action_executed"
        and entry.get("status") == "ok"
        and details.get("capability") == "external.message"
        and details.get("approval_id") == approval_id
        and details.get("destination") == destination
        and details.get("payload_hash") == payload_hash
        and details.get("delivery_receipt_id") == receipt_id
        and details.get("delivery_evidence_sha256") == evidence_hash
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipient", required=True)
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--send", action="store_true",
                    help="Without this the run verifies and stops before delivery.")
    args = ap.parse_args()

    home = Path.home()
    buddy = home / "buddy_core"
    sys.path.insert(0, str(buddy))
    sys.path.insert(0, str(home / "dominion-ops"))
    load_runtime_env(home)

    if not verify_runtime_release(home, args.expected_sha):
        emit("RESULT", "STOP_RUNTIME_RELEASE_MISMATCH")
        return 3

    from core.message_delivery import normalize_email
    from core.operator import BuddyOperator
    from core.authorization import AuthorizationLedger
    emit("IMPORTS", "OK")

    state = Path(os.getenv("BUDDY_STATE_DIR", str(home / ".dominion" / "buddy")))
    operator = BuddyOperator(state_dir=state)
    ledger = AuthorizationLedger(state)
    emit("AUTHORIZATION_LEDGER", "LOADED")
    emit("LEDGER_PENDING_COUNT", len(ledger.pending()))

    from watchmen import saraqael
    chain, _ = stable_saraqael_snapshot(saraqael)
    emit("SARAQAEL_SELF_CHECK", "PASS" if chain.get("valid") else "FAIL")
    emit("SARAQAEL_ENTRIES", chain.get("entries_checked"))
    if not chain.get("valid"):
        emit("SARAQAEL_DETAIL", chain.get("message"))
        emit("RESULT", "STOP_SARAQAEL_INVALID")
        return 4

    cap = operator.capabilities.get("external.message") or {}
    executor_name = cap.get("executor", "")
    registered = executor_name in operator._external_executors
    emit("EXTERNAL_MESSAGE_EXECUTOR", executor_name or "UNDECLARED")
    emit("EXTERNAL_MESSAGE_REGISTERED", "YES" if registered else "NO")
    if not registered:
        emit("RESULT", "STOP_EXECUTOR_UNREGISTERED")
        return 5

    missing = config_report(normalize_email)
    if missing:
        emit("MISSING_CONFIG", ",".join(missing))
        emit("RESULT", "STOP_CONFIG_MISSING")
        return 6

    normalized_recipient = normalize_email(args.recipient)
    if not normalized_recipient or normalized_recipient != args.recipient.strip().lower():
        emit("RESULT", "STOP_RECIPIENT_INVALID")
        return 6

    content_sha = _sha256_text(SUBJECT + "\n" + BODY)
    destination_sha = _sha256_text(normalized_recipient)
    emit("CONTENT_SHA256_EXPECTED", content_sha)
    emit("DESTINATION_SHA256_EXPECTED", destination_sha)
    emit("RECIPIENT_DOMAIN", normalized_recipient.rsplit("@", 1)[-1])

    if not args.send:
        emit("RESULT", "VERIFY_ONLY_NO_SEND")
        return 0

    content = {"subject": SUBJECT, "body_text": BODY, "content_sha256": content_sha}

    def plan(**over):
        step = {"capability": "external.message",
                "instruction": "Send the Founder-authorized Dominion production canary.",
                "content": dict(content), "destination": normalized_recipient}
        step.update(over)
        return {"mission_id": "mission_governed_canary",
                "objective": "Founder-authorized governed delivery canary",
                "steps": [step], "evidence_policy": "HYBRID"}

    first = operator.execute(plan(), session_id="founder_canary")
    emit("FIRST_STATUS", first.get("status"))
    held = first.get("held") or {}
    approval_id = held.get("approval_id", "")
    held_payload_hash = held.get("payload_hash", "")
    emit("HELD", "YES" if first.get("status") == "HELD" and approval_id else "NO")
    emit("AUTHORIZATION_ID", approval_id or "NONE")
    emit("HELD_PAYLOAD_HASH", held_payload_hash or "NONE")
    if first.get("status") != "HELD" or not approval_id or not held_payload_hash:
        emit("RESULT", "STOP_NO_HOLD")
        return 7

    resumed = operator.grant_and_resume(approval_id, session_id="founder_canary",
                                        approver="founder")
    emit("RESUMED_STATUS", resumed.get("status"))
    receipts = [r for r in (resumed.get("receipts") or [])
                if isinstance(r, dict) and r.get("capability") == "external.message"]
    receipt = receipts[-1] if receipts else {}
    emit("RECEIPT_STATUS", receipt.get("status", "NONE"))

    evidence = receipt.get("evidence") or []
    ev = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    receipt_id = ev.get("send_receipt_id") or ev.get("message_id") or ""
    emit("SMTP_MESSAGE_ID", ev.get("message_id", "NONE"))
    emit("SMTP_PROVIDER", ev.get("provider", "NONE"))
    emit("SMTP_OBSERVED_AT", ev.get("observed_at") or ev.get("delivered_at") or "NONE")
    emit("RECEIPT_CONTENT_SHA256", ev.get("content_sha256", "NONE"))
    emit("RECEIPT_DESTINATION_SHA256", ev.get("destination_sha256", "NONE"))
    emit("RECEIPT_ID", receipt_id or "NONE")
    content_matches = ev.get("content_sha256") == content_sha
    destination_matches = ev.get("destination_sha256") == destination_sha
    emit("CONTENT_SHA256_MATCHES", "YES" if content_matches else "NO")
    emit("DESTINATION_SHA256_MATCHES", "YES" if destination_matches else "NO")

    audit = receipt.get("governed_audit") or {}
    emit("SARAQAEL_RECEIPT_SEQ", audit.get("seq", "NONE"))
    emit("SARAQAEL_RECEIPT_HASH", audit.get("hash", "NONE"))

    for err in receipt.get("errors") or []:
        emit("RECEIPT_ERROR", f"{err.get('error')}:{str(err.get('detail'))[:120]}")

    delivered = receipt.get("status") == "VERIFIED"
    emit("DELIVERED", "YES" if delivered else "NO")

    replay = operator.execute(plan(authorization_id=approval_id), session_id="founder_canary")
    replay_receipts = [r for r in (replay.get("receipts") or []) if isinstance(r, dict)]
    replay_last = replay_receipts[-1] if replay_receipts else {}
    replay_errors = replay_last.get("errors") or []
    replay_err = replay_errors[0] if replay_errors and isinstance(replay_errors[0], dict) else {}
    replay_rejected = (
        replay_last.get("status") == "BLOCKED"
        and replay_last.get("attempts") == 0
        and replay_err.get("error") == "AuthorizationRejected"
        and replay_err.get("detail") == "already_consumed"
        and not (replay_last.get("evidence") or [])
    )
    emit("REPLAY_STATUS", replay.get("status"))
    emit("REPLAY_RECEIPT_STATUS", replay_last.get("status", "NONE"))
    emit("REPLAY_ATTEMPTS", replay_last.get("attempts", "NONE"))
    emit("REPLAY_ERROR", replay_err.get("error", "NONE"))
    emit("REPLAY_DETAIL", replay_err.get("detail", "NONE"))
    emit("REPLAY_AUTHORIZATION_REJECTED", "YES" if replay_rejected else "NO")

    final = ledger.load(approval_id) or {}
    emit("AUTHORIZATION_FINAL_STATE", final.get("status", "UNKNOWN"))

    chain_after, entries_after = stable_saraqael_snapshot(saraqael)
    emit("SARAQAEL_CHAIN_AFTER", "VALID" if chain_after.get("valid") else "INVALID")
    emit("SARAQAEL_ENTRIES_AFTER", chain_after.get("entries_checked"))
    audit_bound = governed_audit_matches(
        entries_after,
        audit,
        evidence if isinstance(evidence, list) else [],
        approval_id=approval_id,
        destination=normalized_recipient,
        payload_hash=held_payload_hash,
        receipt_id=receipt_id,
    )
    emit("SARAQAEL_RECEIPT_BOUND", "YES" if audit_bound else "NO")

    ok = (
        delivered
        and replay_rejected
        and content_matches
        and destination_matches
        and audit_bound
        and final.get("status") == "CONSUMED"
        and chain_after.get("valid")
    )
    emit("RESULT", "CANARY_PASS" if ok else "CANARY_FAIL")
    return 0 if ok else 8


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("CANARY_RESULT=EXCEPTION", flush=True)
        traceback.print_exc()
        sys.exit(9)
