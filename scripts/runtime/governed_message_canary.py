"""Verify the deployed Buddy runtime and prove one governed external.message canary.

This runs ON the foundation VM against the deployed checkout. It performs the
whole proof through Buddy's real authority path -- plan, hold, Founder grant,
redemption of the exact frozen payload, delivery, governed audit, replay block.
It never calls the SMTP helper directly, because doing so would bypass the
authorization it is supposed to prove.

It prints presence, identifiers and digests only. No secret value, and no
message body, is ever written to stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

SUBJECT = "Dominion Governed Delivery Canary"
BODY = ("This is a Founder-authorized Dominion production canary proving the "
        "governed external.message execution path. No action is required.")

REQUIRED_SINGLE = ("BUDDY_EXTERNAL_MESSAGE_MODE", "SMTP_HOST", "SMTP_PORT")
REQUIRED_EITHER = (("SMTP_EMAIL", "EMAIL_ADDRESS"), ("SMTP_PASSWORD", "EMAIL_PASSWORD"))

out = []


def emit(key, value):
    line = f"CANARY_{key}={value}"
    out.append(line)
    print(line, flush=True)


def load_runtime_env(home: Path):
    """Load the same dotenv files the Buddy runtime loads, first assignment wins."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        emit("DOTENV", "UNAVAILABLE")
        return
    for candidate in (home / "buddy_core" / ".env", home / "conductor" / ".env", home / ".env"):
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)


def config_report():
    missing = []
    for name in REQUIRED_SINGLE:
        present = bool(str(os.getenv(name) or "").strip())
        emit(f"CONFIG_{name}", "PRESENT" if present else "MISSING")
        if not present:
            missing.append(name)
    for pair in REQUIRED_EITHER:
        present = any(str(os.getenv(n) or "").strip() for n in pair)
        emit(f"CONFIG_{'_OR_'.join(pair)}", "PRESENT" if present else "MISSING")
        if not present:
            missing.append(" or ".join(pair))

    mode = str(os.getenv("BUDDY_EXTERNAL_MESSAGE_MODE") or "").strip().lower()
    emit("CONFIG_MODE_IS_LIVE", "YES" if mode == "live" else f"NO({mode or 'unset'})")
    if mode != "live":
        missing.append("BUDDY_EXTERNAL_MESSAGE_MODE=live")

    sender = str(os.getenv("SMTP_EMAIL") or os.getenv("EMAIL_ADDRESS") or "").strip()
    # Domain only. The local part is never printed.
    emit("CONFIG_SENDER_DOMAIN", sender.rsplit("@", 1)[-1] if "@" in sender else "UNRESOLVED")
    return missing


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

    # ---- deployed revision -------------------------------------------------
    import subprocess
    for label, cwd in (("RUNTIME_SHA", home / "dominion-ops"),):
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(cwd),
                                 capture_output=True, text=True, check=True).stdout.strip()
        except Exception as exc:
            sha = f"UNAVAILABLE({type(exc).__name__})"
        emit(label, sha)
        emit("RUNTIME_SHA_MATCHES_EXPECTED", "YES" if sha == args.expected_sha else "NO")

    # ---- imports / ledger / saraqael / executor ----------------------------
    from core.operator import BuddyOperator
    from core.authorization import AuthorizationLedger
    emit("IMPORTS", "OK")

    state = Path(os.getenv("BUDDY_STATE_DIR", str(home / ".dominion" / "buddy")))
    operator = BuddyOperator(state_dir=state)
    ledger = AuthorizationLedger(state)
    emit("AUTHORIZATION_LEDGER", "LOADED")
    emit("LEDGER_PENDING_COUNT", len(ledger.pending()))

    from watchmen import saraqael
    chain = saraqael.verify_chain()
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

    # ---- required configuration -------------------------------------------
    missing = config_report()
    if missing:
        emit("MISSING_CONFIG", ",".join(missing))
        emit("RESULT", "STOP_CONFIG_MISSING")
        return 6

    content_sha = hashlib.sha256((SUBJECT + "\n" + BODY).encode("utf-8")).hexdigest()
    emit("CONTENT_SHA256_EXPECTED", content_sha)
    emit("RECIPIENT_DOMAIN", args.recipient.rsplit("@", 1)[-1])

    if not args.send:
        emit("RESULT", "VERIFY_ONLY_NO_SEND")
        return 0

    # ---- EVIDENCE -> hold --------------------------------------------------
    content = {"subject": SUBJECT, "body_text": BODY, "content_sha256": content_sha}

    def plan(**over):
        step = {"capability": "external.message",
                "instruction": "Send the Founder-authorized Dominion production canary.",
                "content": dict(content), "destination": args.recipient}
        step.update(over)
        return {"mission_id": "mission_governed_canary",
                "objective": "Founder-authorized governed delivery canary",
                "steps": [step], "evidence_policy": "HYBRID"}

    first = operator.execute(plan(), session_id="founder_canary")
    emit("FIRST_STATUS", first.get("status"))
    held = first.get("held") or {}
    approval_id = held.get("approval_id", "")
    emit("HELD", "YES" if first.get("status") == "HELD" and approval_id else "NO")
    emit("AUTHORIZATION_ID", approval_id or "NONE")
    emit("HELD_PAYLOAD_HASH", held.get("payload_hash", "NONE"))
    if first.get("status") != "HELD" or not approval_id:
        emit("RESULT", "STOP_NO_HOLD")
        return 7

    # ---- FOUNDER AUTHORIZATION -> ACTION (exact stored plan, exact id) -----
    resumed = operator.grant_and_resume(approval_id, session_id="founder_canary",
                                        approver="founder")
    emit("RESUMED_STATUS", resumed.get("status"))
    receipts = [r for r in (resumed.get("receipts") or [])
                if isinstance(r, dict) and r.get("capability") == "external.message"]
    receipt = receipts[-1] if receipts else {}
    emit("RECEIPT_STATUS", receipt.get("status", "NONE"))

    evidence = receipt.get("evidence") or []
    ev = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    emit("SMTP_MESSAGE_ID", ev.get("message_id", "NONE"))
    emit("SMTP_PROVIDER", ev.get("provider", "NONE"))
    emit("SMTP_OBSERVED_AT", ev.get("observed_at") or ev.get("delivered_at") or "NONE")
    emit("RECEIPT_CONTENT_SHA256", ev.get("content_sha256", "NONE"))
    emit("RECEIPT_ID", ev.get("send_receipt_id") or ev.get("message_id") or "NONE")
    emit("CONTENT_SHA256_MATCHES", "YES" if ev.get("content_sha256") == content_sha else "NO")

    audit = receipt.get("governed_audit") or {}
    emit("SARAQAEL_RECEIPT_SEQ", audit.get("seq", "NONE"))
    emit("SARAQAEL_RECEIPT_HASH", audit.get("hash", "NONE"))

    for err in receipt.get("errors") or []:
        emit("RECEIPT_ERROR", f"{err.get('error')}:{str(err.get('detail'))[:120]}")

    delivered = receipt.get("status") == "VERIFIED"
    emit("DELIVERED", "YES" if delivered else "NO")

    # ---- REPLAY BLOCK ------------------------------------------------------
    replay = operator.execute(plan(authorization_id=approval_id), session_id="founder_canary")
    replay_receipts = [r for r in (replay.get("receipts") or []) if isinstance(r, dict)]
    replay_last = replay_receipts[-1] if replay_receipts else {}
    replay_err = (replay_last.get("errors") or [{}])[0]
    emit("REPLAY_STATUS", replay.get("status"))
    emit("REPLAY_DETAIL", replay_err.get("detail", "NONE"))
    replay_blocked = replay.get("status") == "BLOCKED"
    emit("REPLAY_BLOCKED", "YES" if replay_blocked else "NO")

    replay_ev = replay_last.get("evidence") or []
    replay_msg_id = (replay_ev[0].get("message_id")
                     if replay_ev and isinstance(replay_ev[0], dict) else None)
    emit("REPLAY_SENT_SECOND_MESSAGE", "YES" if replay_msg_id else "NO")

    final = ledger.load(approval_id) or {}
    emit("AUTHORIZATION_FINAL_STATE", final.get("status", "UNKNOWN"))

    chain_after = saraqael.verify_chain()
    emit("SARAQAEL_CHAIN_AFTER", "VALID" if chain_after.get("valid") else "INVALID")
    emit("SARAQAEL_ENTRIES_AFTER", chain_after.get("entries_checked"))

    ok = (delivered and replay_blocked and not replay_msg_id
          and ev.get("content_sha256") == content_sha and chain_after.get("valid"))
    emit("RESULT", "CANARY_PASS" if ok else "CANARY_FAIL")
    return 0 if ok else 8


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("CANARY_RESULT=EXCEPTION", flush=True)
        traceback.print_exc()
        sys.exit(9)
