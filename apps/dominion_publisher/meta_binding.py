from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from .vault import CredentialVault


META_SCOPES = (
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class MetaBindingManager:
    """Founder-authorized Meta account discovery and binding.

    OAuth state is HMAC-signed and one-time. Provider tokens are written only to
    the encrypted CredentialVault; API responses expose IDs/labels, never tokens.
    """

    state_ttl_seconds = 10 * 60
    candidate_ttl_minutes = 15
    timeout_seconds = 30

    def __init__(self, vault: CredentialVault, session: requests.Session | None = None) -> None:
        self.vault = vault
        self.session = session or requests.Session()

    def _app(self) -> dict:
        app = self.vault.meta_app()
        if not app:
            raise RuntimeError("Meta app configuration is not present in the encrypted vault")
        return app

    @staticmethod
    def _provider_json(response: requests.Response, operation: str) -> dict:
        if not response.ok:
            details: list[str] = []
            try:
                payload = response.json()
            except (ValueError, TypeError):
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    error_type = str(error.get("type", "")).strip()
                    if error_type:
                        details.append(f"type={error_type}")
                    for field in ("code", "error_subcode"):
                        value = error.get(field)
                        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
                            details.append(f"{field}={value}")
                    fbtrace_id = str(error.get("fbtrace_id", "")).strip()
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", fbtrace_id):
                        details.append(f"fbtrace_id={fbtrace_id}")
            suffix = f" ({', '.join(details)})" if details else ""
            raise RuntimeError(
                f"Meta {operation} failed with HTTP {response.status_code}{suffix}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Meta {operation} returned an invalid response")
        return payload

    def _create_state(self) -> str:
        payload = {
            "nonce": secrets.token_urlsafe(24),
            "exp": int(time.time()) + self.state_ttl_seconds,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self.vault.state_secret(), raw, hashlib.sha256).digest()
        return f"{_b64encode(raw)}.{_b64encode(signature)}"

    def _consume_state(self, state: str) -> None:
        try:
            encoded_payload, encoded_signature = state.split(".", 1)
            raw = _b64decode(encoded_payload)
            signature = _b64decode(encoded_signature)
            expected = hmac.new(self.vault.state_secret(), raw, hashlib.sha256).digest()
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise PermissionError("invalid Meta OAuth state") from exc
        if not hmac.compare_digest(signature, expected):
            raise PermissionError("invalid Meta OAuth state signature")
        nonce = str(payload.get("nonce", "")).strip()
        exp = int(payload.get("exp", 0))
        if not nonce or exp <= int(time.time()):
            raise PermissionError("Meta OAuth state is expired")
        if self.vault.nonce_used(nonce):
            raise PermissionError("Meta OAuth state was already consumed")
        self.vault.mark_nonce_used(nonce)

    def authorization_url(self) -> str:
        """Build the consent URL for whichever login product the app uses.

        Facebook Login for Business draws its permissions from a saved
        configuration and rejects a classic scope list outright -- an app configured
        that way answers a classic scope request with "this app needs at least
        one supported permission", however many permissions are enabled on it.
        So a stored config_id selects that flow, and its absence keeps the
        classic scope flow unchanged.
        """
        app = self._app()
        state = self._create_state()
        params = {
            "client_id": app["app_id"],
            "redirect_uri": app["redirect_uri"],
            "state": state,
            "response_type": "code",
        }
        config_id = str(app.get("config_id", "")).strip()
        if config_id:
            params["config_id"] = config_id
            # Login for Business defaults can return a token-shaped response.
            # Explicitly force the configuration flow to return an exchangeable code.
            params["override_default_response_type"] = "true"
        else:
            params["scope"] = ",".join(META_SCOPES)
        return f"https://www.facebook.com/{app['graph_version']}/dialog/oauth?{urlencode(params)}"

    def _exchange_code(self, code: str) -> str:
        app = self._app()
        base = f"https://graph.facebook.com/{app['graph_version']}"
        response = self.session.post(
            f"{base}/oauth/access_token",
            data={
                "grant_type": "authorization_code",
                "client_id": app["app_id"],
                "client_secret": app["app_secret"],
                "redirect_uri": app["redirect_uri"],
                "code": code,
            },
            timeout=self.timeout_seconds,
        )
        payload = self._provider_json(response, "authorization-code exchange")
        short_token = str(payload.get("access_token", "")).strip()
        if not short_token:
            raise RuntimeError("Meta authorization-code exchange returned no access token")

        response = self.session.get(
            f"{base}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app["app_id"],
                "client_secret": app["app_secret"],
                "fb_exchange_token": short_token,
            },
            timeout=self.timeout_seconds,
        )
        payload = self._provider_json(response, "long-lived token exchange")
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise RuntimeError("Meta long-lived token exchange returned no access token")
        return token

    def _discover_pages(self, user_token: str) -> list[dict]:
        app = self._app()
        base = f"https://graph.facebook.com/{app['graph_version']}"
        response = self.session.get(
            f"{base}/me/accounts",
            params={
                "fields": "id,name,access_token,tasks,instagram_business_account",
                "access_token": user_token,
                "limit": 100,
            },
            timeout=self.timeout_seconds,
        )
        payload = self._provider_json(response, "managed-Page discovery")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("Meta managed-Page discovery returned no data list")
        candidates: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            page_id = str(row.get("id", "")).strip()
            page_name = str(row.get("name", "")).strip()
            page_token = str(row.get("access_token", "")).strip()
            ig = row.get("instagram_business_account")
            ig_id = str(ig.get("id", "")).strip() if isinstance(ig, dict) else ""
            tasks = [str(item) for item in row.get("tasks", []) if isinstance(item, str)]
            if page_id and page_name and page_token:
                candidates.append(
                    {
                        "page_id": page_id,
                        "page_name": page_name,
                        "page_access_token": page_token,
                        "instagram_account_id": ig_id or None,
                        "tasks": tasks,
                    }
                )
        if not candidates:
            raise RuntimeError("Meta returned no managed Pages with Page access tokens")
        return candidates

    def complete_callback(self, *, code: str, state: str) -> list[dict]:
        code = code.strip()
        state = state.strip()
        if not code or not state:
            raise ValueError("Meta OAuth callback requires code and state")
        self._consume_state(state)
        user_token = self._exchange_code(code)
        candidates = self._discover_pages(user_token)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=self.candidate_ttl_minutes)).isoformat()
        self.vault.set_pending_meta(candidates=candidates, expires_at=expires_at)
        return self.vault.pending_meta_safe()
