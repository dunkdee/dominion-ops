from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialVault:
    """Encrypted, VM-local credential store for Dominion Publisher.

    The encryption key and ciphertext are separate mode-0600 files. Secrets are
    never returned by the safe inspection methods and should never be logged.
    """

    schema = "dominion-publisher-credential-vault-v1"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.key_path = self.root / "vault.key"
        self.data_path = self.root / "vault.json.enc"
        self._lock = threading.RLock()
        key = self._load_or_create_key()
        self._fernet = Fernet(key)

    def _load_or_create_key(self) -> bytes:
        if not self.key_path.exists():
            key = Fernet.generate_key()
            try:
                fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(key + b"\n")
        os.chmod(self.key_path, 0o600)
        key = self.key_path.read_bytes().strip()
        Fernet(key)  # validate shape before use
        return key

    @staticmethod
    def _default() -> dict:
        return {
            "schema": CredentialVault.schema,
            "meta_app": None,
            "bindings": {"facebook": {}, "instagram": {}},
            "pending_meta": None,
            "state_secret": secrets.token_urlsafe(48),
            "used_nonces": [],
        }

    def _load_unlocked(self) -> dict:
        if not self.data_path.exists():
            return self._default()
        try:
            raw = self._fernet.decrypt(self.data_path.read_bytes())
        except InvalidToken as exc:
            raise RuntimeError("publisher credential vault cannot be decrypted") from exc
        data = json.loads(raw.decode("utf-8"))
        if data.get("schema") != self.schema:
            raise RuntimeError("unsupported publisher credential vault schema")
        data.setdefault("bindings", {"facebook": {}, "instagram": {}})
        data["bindings"].setdefault("facebook", {})
        data["bindings"].setdefault("instagram", {})
        data.setdefault("pending_meta", None)
        data.setdefault("used_nonces", [])
        if not data.get("state_secret"):
            data["state_secret"] = secrets.token_urlsafe(48)
        return data

    def _save_unlocked(self, data: dict) -> None:
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        encrypted = self._fernet.encrypt(payload)
        tmp = self.data_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.data_path)
            os.chmod(self.data_path, 0o600)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _mutate(self, fn):
        with self._lock:
            data = self._load_unlocked()
            result = fn(data)
            self._save_unlocked(data)
            return result

    def configure_meta_app(
        self,
        *,
        app_id: str,
        app_secret: str,
        redirect_uri: str,
        graph_version: str,
        config_id: str = "",
    ) -> None:
        app_id = app_id.strip()
        app_secret = app_secret.strip()
        redirect_uri = redirect_uri.strip()
        graph_version = graph_version.strip()
        config_id = config_id.strip()
        if not all((app_id, app_secret, redirect_uri, graph_version)):
            raise ValueError("Meta app id, secret, redirect URI, and Graph version are required")
        if not redirect_uri.startswith("https://"):
            raise ValueError("Meta redirect URI must use https")
        if not graph_version.startswith("v"):
            graph_version = f"v{graph_version}"

        def apply(data: dict) -> None:
            data["meta_app"] = {
                "app_id": app_id,
                "app_secret": app_secret,
                "redirect_uri": redirect_uri,
                "graph_version": graph_version,
                # Facebook Login for Business names its permissions in a saved
                # configuration rather than an OAuth scope list. Empty means the
                # app uses classic Facebook Login.
                "config_id": config_id,
                "configured_at": datetime.now(timezone.utc).isoformat(),
            }

        self._mutate(apply)

    def meta_app(self) -> dict | None:
        with self._lock:
            app = self._load_unlocked().get("meta_app")
            return dict(app) if app else None

    def state_secret(self) -> bytes:
        with self._lock:
            data = self._load_unlocked()
            secret = data.get("state_secret")
            if not secret:
                secret = secrets.token_urlsafe(48)
                data["state_secret"] = secret
                self._save_unlocked(data)
            return secret.encode("utf-8")

    def nonce_used(self, nonce: str) -> bool:
        with self._lock:
            return nonce in self._load_unlocked().get("used_nonces", [])

    def mark_nonce_used(self, nonce: str) -> None:
        def apply(data: dict) -> None:
            used = [item for item in data.get("used_nonces", []) if isinstance(item, str)]
            if nonce not in used:
                used.append(nonce)
            data["used_nonces"] = used[-200:]

        self._mutate(apply)

    def set_pending_meta(self, *, candidates: list[dict], expires_at: str) -> None:
        if not candidates:
            raise ValueError("no Meta account candidates were returned")
        clean: list[dict] = []
        for candidate in candidates:
            page_id = str(candidate.get("page_id", "")).strip()
            page_name = str(candidate.get("page_name", "")).strip()
            page_token = str(candidate.get("page_access_token", "")).strip()
            if not page_id or not page_name or not page_token:
                continue
            ig_id = str(candidate.get("instagram_account_id") or "").strip() or None
            tasks = [str(item) for item in candidate.get("tasks", []) if isinstance(item, str)]
            clean.append(
                {
                    "page_id": page_id,
                    "page_name": page_name,
                    "page_access_token": page_token,
                    "instagram_account_id": ig_id,
                    "tasks": tasks,
                }
            )
        if not clean:
            raise ValueError("Meta returned no bindable Pages")

        def apply(data: dict) -> None:
            data["pending_meta"] = {"expires_at": expires_at, "candidates": clean}

        self._mutate(apply)

    @staticmethod
    def _pending_is_expired(pending: dict | None) -> bool:
        if not pending:
            return True
        try:
            expires = datetime.fromisoformat(str(pending["expires_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return True
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires <= datetime.now(timezone.utc)

    def pending_meta_safe(self) -> list[dict]:
        with self._lock:
            pending = self._load_unlocked().get("pending_meta")
            if self._pending_is_expired(pending):
                return []
            return [
                {
                    "page_id": item["page_id"],
                    "page_name": item["page_name"],
                    "instagram_account_id": item.get("instagram_account_id"),
                    "tasks": list(item.get("tasks", [])),
                }
                for item in pending.get("candidates", [])
            ]

    def bind_page(self, *, page_id: str, approved_by: str) -> dict:
        page_id = page_id.strip()
        approved_by = approved_by.strip()
        if not page_id or not approved_by:
            raise ValueError("page_id and approved_by are required")

        def apply(data: dict) -> dict:
            pending = data.get("pending_meta")
            if self._pending_is_expired(pending):
                raise RuntimeError("Meta binding session is missing or expired")
            candidate = next(
                (item for item in pending.get("candidates", []) if item.get("page_id") == page_id),
                None,
            )
            if candidate is None:
                raise ValueError("requested Facebook Page is not in the approved binding candidates")
            now = datetime.now(timezone.utc).isoformat()
            common = {
                "page_id": candidate["page_id"],
                "page_name": candidate["page_name"],
                "access_token": candidate["page_access_token"],
                "tasks": list(candidate.get("tasks", [])),
                "approved_by": approved_by,
                "bound_at": now,
            }
            data["bindings"]["facebook"][candidate["page_id"]] = dict(common)
            ig_id = candidate.get("instagram_account_id")
            if ig_id:
                ig = dict(common)
                ig["instagram_account_id"] = ig_id
                data["bindings"]["instagram"][ig_id] = ig
            data["pending_meta"] = None
            return {
                "facebook": {
                    "account_id": candidate["page_id"],
                    "label": candidate["page_name"],
                },
                "instagram": (
                    {"account_id": ig_id, "label": candidate["page_name"]} if ig_id else None
                ),
                "approved_by": approved_by,
                "bound_at": now,
            }

        return self._mutate(apply)

    def token_for(self, platform: str, account_id: str) -> str:
        with self._lock:
            data = self._load_unlocked()
            item = data.get("bindings", {}).get(platform, {}).get(account_id)
            return str(item.get("access_token", "")).strip() if item else ""

    def graph_version(self) -> str:
        app = self.meta_app()
        return str(app.get("graph_version", "")).strip() if app else ""

    def bound_accounts_safe(self) -> dict[str, list[dict]]:
        with self._lock:
            bindings = self._load_unlocked().get("bindings", {})
            result: dict[str, list[dict]] = {"facebook": [], "instagram": []}
            for platform in result:
                for account_id, item in bindings.get(platform, {}).items():
                    result[platform].append(
                        {
                            "account_id": account_id,
                            "label": item.get("page_name"),
                            "approved_by": item.get("approved_by"),
                            "bound_at": item.get("bound_at"),
                        }
                    )
            return result
