from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_all(text: str, old: str, new: str, label: str, minimum: int = 1) -> str:
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{label}: expected at least {minimum} matches, found {count}")
    return text.replace(old, new)


def replace_region(text: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"{label}: start marker missing")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"{label}: end marker missing")
    return text[:start] + replacement + text[end:]


def patch_authorization() -> None:
    rel = "buddy_core/core/authorization.py"
    text = read(rel)
    text = replace_once(
        text,
        "import hashlib\nimport json\nimport os\nimport tempfile\nimport uuid\n",
        "import hashlib\nimport hmac\nimport json\nimport os\nimport secrets\nimport stat\nimport tempfile\nimport uuid\n",
        "authorization imports",
    )
    text = replace_once(
        text,
        "* **Tamper-evident.** ``approval_hash`` covers the whole record, so a granted\n  authorization cannot be edited after the fact without detection.\n",
        "* **Authenticated.** ``approval_hash`` is an HMAC-SHA256 over the whole\n  record using a machine-local secret outside writable Buddy state. A process\n  that can edit ledger JSON cannot manufacture Founder authority.\n",
        "authorization doc integrity",
    )
    text = replace_once(
        text,
        "SCHEMA = \"dominion-founder-authorization-v1\"\n",
        "SCHEMA = \"dominion-founder-authorization-v1\"\nAUTH_HMAC_ENV = \"DOMINION_AUTHORIZATION_HMAC_KEY\"\nAUTH_HMAC_FILE_ENV = \"DOMINION_AUTHORIZATION_HMAC_KEY_FILE\"\nAUTH_DEFAULT_KEY_FILE = Path.home() / \".dominion\" / \"authorization\" / \"ledger_hmac.key\"\n",
        "authorization constants",
    )
    text = replace_once(
        text,
        "def _hash_without(record: dict, field: str) -> str:\n    return sha256_json({k: v for k, v in record.items() if k != field})\n\n\n",
        "def _record_mac_material(record: dict) -> bytes:\n    return canonical_json({k: v for k, v in record.items() if k != \"approval_hash\"}).encode(\"utf-8\")\n\n\ndef _path_within(path: Path, parent: Path) -> bool:\n    path = path.resolve(strict=False)\n    parent = parent.resolve(strict=False)\n    return path == parent or parent in path.parents\n\n\ndef _detect_checkout_root(start: Path | None = None) -> Path | None:\n    current = (start or Path(__file__)).resolve(strict=False)\n    if current.is_file():\n        current = current.parent\n    for candidate in (current, *current.parents):\n        if (candidate / \".git\").exists():\n            return candidate.resolve(strict=False)\n        if (candidate / \".github\").is_dir() and (candidate / \"buddy_core\").is_dir():\n            return candidate.resolve(strict=False)\n    return None\n\n\ndef _validate_auth_key(raw: bytes, origin: str) -> bytes:\n    key = raw.strip()\n    if len(key) < 32:\n        raise AuthorizationError(f\"authorization signing key from {origin} is weaker than 256 bits\")\n    return key\n\n\n",
        "authorization mac helpers",
    )
    text = replace_once(
        text,
        "    def __init__(self, state_dir: Path | str):\n        self.root = Path(state_dir) / \"authorizations\"\n        self.root.mkdir(parents=True, exist_ok=True)\n        self.receipts_path = self.root / \"receipts.jsonl\"\n        self.sequence_path = self.root / \"sequence.json\"\n        self.lock_path = self.root / \".ledger.lock\"\n\n    # ── storage ──────────────────────────────────────────────────────────\n",
        "    def __init__(self, state_dir: Path | str):\n        self.state_dir = Path(state_dir).expanduser().resolve(strict=False)\n        self.root = self.state_dir / \"authorizations\"\n        self.root.mkdir(parents=True, exist_ok=True)\n        self.receipts_path = self.root / \"receipts.jsonl\"\n        self.sequence_path = self.root / \"sequence.json\"\n        self.lock_path = self.root / \".ledger.lock\"\n        self._hmac_key = self._resolve_signing_key()\n\n    def _resolve_signing_key(self) -> bytes:\n        direct = os.environ.get(AUTH_HMAC_ENV)\n        if direct is not None:\n            return _validate_auth_key(direct.encode(\"utf-8\"), f\"${AUTH_HMAC_ENV}\")\n\n        configured = os.environ.get(AUTH_HMAC_FILE_ENV)\n        if configured is not None and not configured.strip():\n            raise AuthorizationError(f\"${AUTH_HMAC_FILE_ENV} is set but empty\")\n        path = (\n            Path(configured.strip()).expanduser().resolve(strict=False)\n            if configured is not None\n            else AUTH_DEFAULT_KEY_FILE.expanduser().resolve(strict=False)\n        )\n\n        source_root = Path(__file__).resolve(strict=False).parents[1]\n        checkout_root = _detect_checkout_root(Path(__file__))\n        if _path_within(path, self.state_dir):\n            raise AuthorizationError(\"authorization signing key must be outside writable Buddy state\")\n        if _path_within(path, source_root):\n            raise AuthorizationError(\"authorization signing key must be outside Buddy source\")\n        if checkout_root is not None and _path_within(path, checkout_root):\n            raise AuthorizationError(\"authorization signing key must be outside repository checkout\")\n\n        try:\n            path.parent.mkdir(parents=True, exist_ok=True)\n            if os.name == \"posix\":\n                os.chmod(path.parent, 0o700)\n                if stat.S_IMODE(path.parent.stat().st_mode) != 0o700:\n                    raise AuthorizationError(\"authorization signing key directory is not private\")\n        except AuthorizationError:\n            raise\n        except OSError as exc:\n            raise AuthorizationError(\"authorization signing key directory unavailable\") from exc\n\n        def read_existing() -> bytes:\n            try:\n                if os.name == \"posix\" and stat.S_IMODE(path.stat().st_mode) & 0o077:\n                    raise AuthorizationError(\"authorization signing key file is not private\")\n                return _validate_auth_key(path.read_bytes(), str(path))\n            except AuthorizationError:\n                raise\n            except OSError as exc:\n                raise AuthorizationError(\"authorization signing key file unreadable\") from exc\n\n        if path.exists():\n            return read_existing()\n\n        key = secrets.token_hex(32).encode(\"ascii\")\n        fd = None\n        try:\n            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n            if os.name == \"posix\" and hasattr(os, \"fchmod\"):\n                os.fchmod(fd, 0o600)\n            with os.fdopen(fd, \"wb\") as fh:\n                fd = None\n                fh.write(key + b\"\\n\")\n                fh.flush()\n                os.fsync(fh.fileno())\n            if os.name == \"posix\":\n                dir_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, \"O_DIRECTORY\", 0))\n                try:\n                    os.fsync(dir_fd)\n                finally:\n                    os.close(dir_fd)\n                os.chmod(path, 0o600)\n                if stat.S_IMODE(path.stat().st_mode) != 0o600:\n                    raise AuthorizationError(\"authorization signing key file is not private\")\n            return key\n        except FileExistsError:\n            return read_existing()\n        except AuthorizationError:\n            raise\n        except OSError as exc:\n            raise AuthorizationError(\"authorization signing key generation failed\") from exc\n        finally:\n            if fd is not None:\n                try:\n                    os.close(fd)\n                except OSError:\n                    pass\n\n    def _record_mac(self, record: dict) -> str:\n        return hmac.new(self._hmac_key, _record_mac_material(record), hashlib.sha256).hexdigest()\n\n    def _record_mac_valid(self, record: dict) -> bool:\n        supplied = record.get(\"approval_hash\")\n        if not isinstance(supplied, str) or len(supplied) != 64:\n            return False\n        return hmac.compare_digest(supplied, self._record_mac(record))\n\n    # ── storage ──────────────────────────────────────────────────────────\n",
        "authorization init and key boundary",
    )
    old_next = '''    def _next_sequence(self) -> int:\n        current = 0\n        if self.sequence_path.is_file():\n            try:\n                current = int(json.loads(self.sequence_path.read_text(encoding="utf-8"))["sequence"])\n            except (OSError, ValueError, KeyError, TypeError):\n                current = 0\n        nxt = current + 1\n        self._atomic_write_text(\n            self.sequence_path, canonical_json({"sequence": nxt}) + "\\n"\n        )\n        return nxt\n'''
    new_next = '''    def _next_sequence(self) -> int:\n        # Derive monotonic authority from authenticated records, not a mutable cache.\n        current = 0\n        for path in self.root.glob("approval_*.json"):\n            try:\n                record = json.loads(path.read_text(encoding="utf-8"))\n            except (OSError, ValueError):\n                continue\n            if not self._record_mac_valid(record):\n                continue\n            try:\n                current = max(current, int(record.get("authorization_sequence") or 0))\n            except (TypeError, ValueError):\n                continue\n        nxt = current + 1\n        self._atomic_write_text(\n            self.sequence_path, canonical_json({"sequence": nxt}) + "\\n"\n        )\n        return nxt\n'''
    text = replace_once(text, old_next, new_next, "authorization monotonic sequence")
    text = replace_all(
        text,
        'record["approval_hash"] = _hash_without(record, "approval_hash")',
        'record["approval_hash"] = self._record_mac(record)',
        "authorization sign transitions",
        minimum=4,
    )
    text = replace_all(
        text,
        'record.get("approval_hash") != _hash_without(record, "approval_hash")',
        'not self._record_mac_valid(record)',
        "authorization verify transitions",
        minimum=2,
    )
    text = replace_once(
        text,
        '            except (OSError, ValueError):\n                continue\n            if record.get("status") != PENDING:\n',
        '            except (OSError, ValueError):\n                continue\n            if not self._record_mac_valid(record):\n                continue\n            if record.get("status") != PENDING:\n',
        "authorization pending integrity",
    )
    text = replace_once(
        text,
        '    def _deny_locked(self, approval_id: str, *, approver: str = "founder", reason: str = "") -> dict:\n        record = self.load(approval_id)\n        if record is None:\n            return {"ok": False, "error": "unknown_approval_id"}\n        if record.get("status") in {CONSUMED, DENIED}:\n',
        '    def _deny_locked(self, approval_id: str, *, approver: str = "founder", reason: str = "") -> dict:\n        record = self.load(approval_id)\n        if record is None:\n            return {"ok": False, "error": "unknown_approval_id"}\n        if not self._record_mac_valid(record):\n            return {"ok": False, "error": "authorization_record_tampered"}\n        if record.get("status") in {CONSUMED, DENIED}:\n',
        "authorization deny integrity",
    )
    if "_hash_without(" in text:
        raise SystemExit("authorization: legacy unkeyed record hash remains")
    write(rel, text)


def patch_operator() -> None:
    rel = "buddy_core/core/operator.py"
    text = read(rel)
    validator = '''    @staticmethod\n    def _validate_delivery_evidence(capability: str, evidence: Any) -> tuple[bool, str | None]:\n        """Validate the exact receipt contract for every consequential capability."""\n        if not isinstance(evidence, list) or not evidence:\n            return False, None\n\n        def scalar(item: dict, keys: tuple[str, ...]) -> str | None:\n            for key in keys:\n                value = item.get(key)\n                if isinstance(value, (str, int, float)) and not isinstance(value, bool):\n                    rendered = str(value).strip()\n                    if rendered:\n                        return rendered\n            return None\n\n        provenance_keys = ("platform", "provider", "system", "source")\n        time_keys = ("observed_at", "delivered_at", "timestamp", "created_at")\n        id_keys = {\n            "external.publish": ("platform_receipt_id", "publication_id", "post_id", "receipt_id"),\n            "external.message": ("send_receipt_id", "message_id", "receipt_id"),\n            "external.spend": ("financial_receipt_id", "transaction_id", "payment_id", "receipt_id"),\n            "external.submit": ("submission_receipt_id", "submission_id", "filing_id"),\n            "external.browser": ("browser_action_receipt_id", "browser_action_id", "action_id"),\n            "external.credential_or_network": ("change_receipt_id", "network_change_id", "credential_change_id"),\n        }\n        if capability not in id_keys:\n            return False, None\n\n        for item in evidence:\n            if not isinstance(item, dict) or not item:\n                continue\n            receipt_id = scalar(item, id_keys[capability])\n            provenance = scalar(item, provenance_keys)\n            observed_at = scalar(item, time_keys)\n            if not (receipt_id and provenance and observed_at):\n                continue\n\n            if capability == "external.browser":\n                if not scalar(item, ("action", "action_type", "browser_action")):\n                    continue\n            elif capability == "external.credential_or_network":\n                before = item.get("before_state")\n                after = item.get("after_state")\n                verification = item.get("verification")\n                rollback = scalar(item, ("rollback_receipt_id", "rollback_id"))\n                json_native = (str, int, float, bool, dict, list)\n                if before is None or after is None or not isinstance(before, json_native) or not isinstance(after, json_native):\n                    continue\n                verified = (\n                    verification is True\n                    or (isinstance(verification, dict) and verification.get("ok") is True)\n                    or (isinstance(verification, str) and verification.strip().lower() in {"ok", "passed", "verified"})\n                )\n                if not verified or not rollback:\n                    continue\n            return True, receipt_id\n        return False, None\n\n    @staticmethod\n    def _authorized_external_context(step: dict) -> dict:\n        # Every value exposed to the executor is already included in payload_fingerprint().\n        return {\n            "capability": step["capability"],\n            "instruction": step["instruction"],\n            "content": copy.deepcopy(step.get("content")),\n            "destination": step.get("destination"),\n        }\n\n'''
    text = replace_region(
        text,
        "    @staticmethod\n    def _validate_delivery_evidence",
        "    def _execute_external",
        validator,
        "operator receipt validator",
    )
    text = replace_once(
        text,
        "            outcome = executor(step, context)\n",
        "            outcome = executor(copy.deepcopy(step), self._authorized_external_context(step))\n",
        "operator authorized executor context",
    )
    old_hash = '''        evidence_hash = hashlib.sha256(\n            json.dumps(\n                evidence,\n                sort_keys=True,\n                ensure_ascii=True,\n                separators=(",", ":"),\n            ).encode("utf-8")\n        ).hexdigest()\n'''
    new_hash = '''        try:\n            evidence_blob = json.dumps(\n                evidence,\n                sort_keys=True,\n                ensure_ascii=True,\n                separators=(",", ":"),\n                allow_nan=False,\n            ).encode("utf-8")\n            # A non-serializable result would fail later persistence/HTTP response after\n            # a real side effect, so reject it here while preserving delivered truth.\n            json.dumps(outcome.get("result"), ensure_ascii=True, allow_nan=False)\n        except (TypeError, ValueError, OverflowError) as exc:\n            return {**base, "status": "DELIVERED_UNVERIFIED",\n                    "errors": [{"attempt": 1, "error": "EvidenceSerializationError",\n                                "detail": type(exc).__name__}],\n                    "result": None,\n                    "evidence": [{"type": "delivery_evidence_rejected",\n                                  "reason": "non_json_serializable"}]}\n        evidence_hash = hashlib.sha256(evidence_blob).hexdigest()\n'''
    text = replace_once(text, old_hash, new_hash, "operator evidence serialization")
    write(rel, text)


def patch_buddy_web() -> None:
    rel = "buddy_core/buddy_web.py"
    text = read(rel)
    text = replace_once(
        text,
        "  .input-area button:disabled { opacity:0.35; }\n  .typing { color:var(--gold); font-size:12px; padding:4px 16px; letter-spacing:.1em; }\n",
        "  .input-area button:disabled { opacity:0.35; }\n  .approval-card{border:1px solid rgba(201,162,42,.32);padding:12px 14px;margin:6px 0;background:rgba(201,162,42,.06)}\n  .approval-card .approval-id{font-size:10px;opacity:.65;word-break:break-all;margin-top:6px}\n  .approval-card button{margin-top:10px;background:var(--gold);color:var(--void);border:0;padding:10px 14px;font-weight:700;cursor:pointer}\n  .approval-card button:disabled{opacity:.4;cursor:default}\n  .typing { color:var(--gold); font-size:12px; padding:4px 16px; letter-spacing:.1em; }\n",
        "buddy approval css",
    )
    text = replace_once(
        text,
        "    addMsg(data.response || 'No response.', 'buddy');\n    speakText(data.response || '');\n",
        "    addMsg(data.response || 'No response.', 'buddy');\n    if (data.held && data.held.approval_id) renderHeldApproval(data.held);\n    speakText(data.response || '');\n",
        "buddy render held response",
    )
    functions = '''\nfunction renderHeldApproval(held) {\n  const approvalId = String((held && held.approval_id) || '');\n  if (!/^approval_[0-9a-f]{12}$/.test(approvalId)) {\n    addMsg('Held action returned an invalid authorization reference. Approval blocked.', 'system');\n    return;\n  }\n  const card = document.createElement('div');\n  card.className = 'msg system approval-card';\n  const title = document.createElement('div');\n  title.textContent = 'Founder approval required: ' + String(held.capability || 'external action');\n  const detail = document.createElement('div');\n  detail.className = 'approval-id';\n  detail.textContent = approvalId;\n  const approve = document.createElement('button');\n  approve.type = 'button';\n  approve.textContent = 'APPROVE & RESUME';\n  approve.addEventListener('click', () => approveHeld(approvalId, approve, card));\n  card.appendChild(title);\n  card.appendChild(detail);\n  card.appendChild(approve);\n  msgs.appendChild(card);\n  msgs.scrollTop = msgs.scrollHeight;\n}\n\nasync function approveHeld(approvalId, approveButton, card) {\n  if (!/^approval_[0-9a-f]{12}$/.test(approvalId)) return;\n  approveButton.disabled = true;\n  approveButton.textContent = 'APPROVING...';\n  try {\n    const r = await fetch('/buddy/api/chat', {\n      method: 'POST',\n      headers: {'Content-Type':'application/json'},\n      credentials: 'same-origin',\n      body: JSON.stringify({approve: true, authorization_id: approvalId, session_id: sessionId})\n    });\n    if (r.status === 401 || r.status === 403) { window.location.replace('/buddy/login'); return; }\n    const data = await r.json().catch(() => ({}));\n    card.remove();\n    addMsg(data.response || data.error || data.status || 'Approval processed.', 'buddy');\n    if (data.held && data.held.approval_id) renderHeldApproval(data.held);\n    speakText(data.response || '');\n  } catch(e) {\n    approveButton.disabled = false;\n    approveButton.textContent = 'APPROVE & RESUME';\n    addMsg('Approval connection lost. Nothing was re-authorized automatically.', 'system');\n  }\n}\n\n'''
    text = replace_once(text, "function addMsg(text, type) {\n", functions + "function addMsg(text, type) {\n", "buddy explicit approval functions")
    write(rel, text)


def patch_saraqael() -> None:
    rel = "buddy_core/watchmen/saraqael.py"
    text = read(rel)
    old_state = '''def state_dir() -> Path:\n    """Resolve machine-local audit state and reject any path inside this checkout."""\n    override = os.environ.get(ENV_STATE_DIR, "").strip()\n    candidate = (Path(override).expanduser() if override else DEFAULT_STATE_DIR).resolve(strict=False)\n    repo_root = _BASE_DIR.parent.resolve(strict=False)\n    if candidate == repo_root or repo_root in candidate.parents:\n        raise WatchmenStateError(\n            f"audit state directory must be outside the repository checkout: {candidate}"\n        )\n    return candidate\n\n\n'''
    new_state = '''def _path_within(path: Path, parent: Path) -> bool:\n    path = path.resolve(strict=False)\n    parent = parent.resolve(strict=False)\n    return path == parent or parent in path.parents\n\n\ndef _detect_checkout_root(start: Path | None = None) -> Path | None:\n    """Return a concrete checkout root; never infer HOME merely from layout."""\n    current = (start or _BASE_DIR).resolve(strict=False)\n    if current.is_file():\n        current = current.parent\n    for candidate in (current, *current.parents):\n        if (candidate / ".git").exists():\n            return candidate.resolve(strict=False)\n        if (candidate / ".github").is_dir() and (candidate / "buddy_core").is_dir():\n            return candidate.resolve(strict=False)\n    return None\n\n\ndef _path_is_source_controlled(path: Path) -> bool:\n    candidate = path.expanduser().resolve(strict=False)\n    # Always protect the runtime Buddy source tree, even in a copied deployment\n    # that intentionally has no .git metadata.\n    if _path_within(candidate, _BASE_DIR):\n        return True\n    checkout = _detect_checkout_root(_BASE_DIR)\n    return checkout is not None and _path_within(candidate, checkout)\n\n\ndef state_dir() -> Path:\n    """Resolve machine-local audit state without aliasing $HOME to a checkout."""\n    override = os.environ.get(ENV_STATE_DIR, "").strip()\n    candidate = (Path(override).expanduser() if override else DEFAULT_STATE_DIR).resolve(strict=False)\n    if _path_is_source_controlled(candidate):\n        raise WatchmenStateError(\n            f"audit state directory must be outside Buddy source/repository checkout: {candidate}"\n        )\n    return candidate\n\n\n'''
    text = replace_once(text, old_state, new_state, "saraqael checkout detection")
    text = replace_once(
        text,
        '''    env_file = os.environ.get(ENV_HMAC_FILE)\n    if env_file is not None:\n        path = Path(env_file.strip()).expanduser()\n        if not env_file.strip():\n            raise WatchmenStateError(f"${ENV_HMAC_FILE} is set but empty")\n        try:\n            _assert_private_file(path, label="explicit audit signing key file")\n            raw = path.read_bytes()\n''',
        '''    env_file = os.environ.get(ENV_HMAC_FILE)\n    if env_file is not None:\n        if not env_file.strip():\n            raise WatchmenStateError(f"${ENV_HMAC_FILE} is set but empty")\n        path = Path(env_file.strip()).expanduser().resolve(strict=False)\n        if _path_is_source_controlled(path):\n            raise WatchmenStateError(\n                f"explicit audit signing key file must be outside Buddy source/repository checkout: {path}"\n            )\n        try:\n            _assert_private_file(path, label="explicit audit signing key file")\n            raw = path.read_bytes()\n''',
        "saraqael explicit key boundary",
    )
    write(rel, text)


def write_tests() -> None:
    rel = ROOT / "tests/test_pr235_final_security_closure.py"
    rel.write_text(r'''from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buddy_core.core import authorization as auth
from buddy_core.core.operator import BuddyOperator
from buddy_core.watchmen import saraqael


@pytest.fixture
def authority_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMINION_AUTHORIZATION_HMAC_KEY", "A" * 32)
    monkeypatch.setenv("DOMINION_WATCHMEN_HMAC_KEY", "W" * 32)
    monkeypatch.setenv("DOMINION_WATCHMEN_STATE_DIR", str(tmp_path / "watchmen"))
    return tmp_path


def test_public_checksum_cannot_forge_founder_authority(authority_env):
    ledger = auth.AuthorizationLedger(authority_env / "buddy")
    req = ledger.request(
        mission_id="m1", step=1, capability="external.publish",
        instruction="publish approved", content="exact", destination="dest",
    )
    path = ledger._path(req["approval_id"])
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["status"] = auth.GRANTED
    forged["approver"] = "attacker"
    forged["authorization_sequence"] = 999
    # Recompute the legacy public checksum exactly as an attacker could.
    forged["approval_hash"] = auth.sha256_json(
        {k: v for k, v in forged.items() if k != "approval_hash"}
    )
    path.write_text(auth.canonical_json(forged) + "\n", encoding="utf-8")
    result = ledger.verify_and_consume(
        req["approval_id"], capability="external.publish",
        instruction="publish approved", content="exact", destination="dest",
    )
    assert result == {"ok": False, "error": "authorization_record_tampered"}


def test_weak_authorization_hmac_key_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMINION_AUTHORIZATION_HMAC_KEY", "short")
    with pytest.raises(auth.AuthorizationError, match="weaker than 256 bits"):
        auth.AuthorizationLedger(tmp_path / "buddy")


def test_external_executor_cannot_receive_regenerated_unbound_context(authority_env):
    op = BuddyOperator(state_dir=authority_env / "buddy")
    captured = {}

    def executor(step, context):
        captured["step"] = step
        captured["context"] = context
        return {
            "delivered": True,
            "result": {"ok": True},
            "evidence": [{
                "publication_id": "post-1",
                "platform": "test-platform",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }],
        }

    op._external_executors["external:publish"] = executor
    step = {
        "capability": "external.publish",
        "instruction": "publish exact",
        "content": "AUTHORIZED CONTENT",
        "destination": "authorized-destination",
    }
    cap = op.capabilities["external.publish"]
    context = {"outputs": ["REGENERATED ATTACK CONTENT"], "secret": "must-not-cross"}
    receipt = op._execute_external(
        1, step, cap, context,
        {"approval_id": "approval_aaaaaaaaaaaa", "authorization_sequence": 1,
         "payload_hash": "p" * 64, "approver": "founder"},
    )
    assert receipt["status"] == "VERIFIED"
    assert captured["context"] == {
        "capability": "external.publish",
        "instruction": "publish exact",
        "content": "AUTHORIZED CONTENT",
        "destination": "authorized-destination",
    }
    assert "REGENERATED ATTACK CONTENT" not in json.dumps(captured["context"])
    assert "secret" not in captured["context"]


def test_receipt_contracts_cover_every_external_capability():
    common = {"source": "provider", "observed_at": "2026-09-05T00:00:00Z"}
    assert BuddyOperator._validate_delivery_evidence(
        "external.submit", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    assert BuddyOperator._validate_delivery_evidence(
        "external.submit", [{**common, "submission_id": "sub-1"}]
    ) == (True, "sub-1")

    assert BuddyOperator._validate_delivery_evidence(
        "external.browser", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    assert BuddyOperator._validate_delivery_evidence(
        "external.browser", [{**common, "browser_action_id": "act-1", "action": "submit_form"}]
    ) == (True, "act-1")

    assert BuddyOperator._validate_delivery_evidence(
        "external.credential_or_network", [{**common, "receipt_id": "generic"}]
    ) == (False, None)
    strong = {
        **common,
        "network_change_id": "chg-1",
        "before_state": {"port": "closed"},
        "after_state": {"port": "closed"},
        "verification": {"ok": True},
        "rollback_receipt_id": "rb-1",
    }
    assert BuddyOperator._validate_delivery_evidence(
        "external.credential_or_network", [strong]
    ) == (True, "chg-1")


def test_non_json_delivery_evidence_returns_truthful_receipt(authority_env):
    op = BuddyOperator(state_dir=authority_env / "buddy")

    class NotJson:
        pass

    def executor(step, context):
        return {
            "delivered": True,
            "result": {"ok": True},
            "evidence": [{
                "publication_id": "post-2",
                "platform": "test-platform",
                "observed_at": "2026-09-05T00:00:00Z",
                "opaque": NotJson(),
            }],
        }

    op._external_executors["external:publish"] = executor
    receipt = op._execute_external(
        1,
        {"capability": "external.publish", "instruction": "x", "content": "y", "destination": "z"},
        op.capabilities["external.publish"], {},
        {"approval_id": "approval_bbbbbbbbbbbb", "authorization_sequence": 2,
         "payload_hash": "q" * 64, "approver": "founder"},
    )
    assert receipt["status"] == "DELIVERED_UNVERIFIED"
    assert receipt["errors"][0]["error"] == "EvidenceSerializationError"
    json.dumps(receipt)


def test_copied_buddy_layout_does_not_treat_home_as_checkout(tmp_path):
    fake = tmp_path / "home" / "buddy_core" / "watchmen" / "saraqael.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# copied runtime\n", encoding="utf-8")
    assert saraqael._detect_checkout_root(fake) is None


def test_explicit_watchmen_key_inside_source_is_rejected(monkeypatch):
    inside = Path(saraqael.__file__).resolve().parent / "forbidden-test.key"
    monkeypatch.delenv(saraqael.ENV_HMAC_KEY, raising=False)
    monkeypatch.setenv(saraqael.ENV_HMAC_FILE, str(inside))
    with pytest.raises(saraqael.WatchmenStateError, match="outside Buddy source"):
        saraqael._resolve_key()


def test_browser_chat_exposes_explicit_exact_id_approval_control():
    from buddy_core import buddy_web

    html = buddy_web.CHAT_HTML
    assert "renderHeldApproval" in html
    assert "approveHeld" in html
    assert "authorization_id: approvalId" in html
    assert "APPROVE & RESUME" in html
    assert "approve: true" in html
''', encoding="utf-8")


def main() -> None:
    patch_authorization()
    patch_operator()
    patch_buddy_web()
    patch_saraqael()
    write_tests()
    print("PR235 final security closure applied")


if __name__ == "__main__":
    main()
