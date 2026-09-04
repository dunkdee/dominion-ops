"""End-to-end phone sign-in for Buddy Web.

Exercises the real FastAPI app: sign-in screen, passcode exchange, signed
session cookie, and the existing dashboard opening on success. No new service
and no new dashboard — /buddy still serves the chat cockpit it always did.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "master-token-8f2b41c6d5e09a7b3c1d4e6f"
PASSCODE = "DominionPhone2026"


def load_app(token: str = TOKEN, passcode: str = PASSCODE, **extra):
    """Import buddy_web fresh under a controlled environment."""
    saved = dict(os.environ)
    os.environ["BUDDY_WEB_TOKEN"] = token
    os.environ["BUDDY_PHONE_PASSCODE"] = passcode
    os.environ.pop("BUDDY_ALLOW_OPEN_DEV", None)
    os.environ.update(extra)
    try:
        for name in ("buddy_core.buddy_web", "buddy_web"):
            sys.modules.pop(name, None)
        module = importlib.import_module("buddy_core.buddy_web")
        return importlib.reload(module)
    finally:
        os.environ.clear()
        os.environ.update(saved)


class PhoneLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_app()

    def setUp(self):
        self.module._login_failures.clear()
        self.client = TestClient(self.module.app)

    # ── the phone's first visit ──────────────────────────────────────────

    def test_unauthenticated_dashboard_serves_the_sign_in_screen_as_401(self):
        # 401 keeps every existing production gate and machine probe honest;
        # the HTML body is what makes it usable from a phone browser.
        r = self.client.get("/buddy")
        self.assertEqual(r.status_code, 401)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("/buddy/api/login", r.text)
        self.assertIn("Passcode", r.text)
        self.assertNotIn(TOKEN, r.text)
        self.assertNotIn(PASSCODE, r.text)

    def test_login_page_is_reachable_without_credentials(self):
        r = self.client.get("/buddy/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Unlock Buddy", r.text)

    def test_login_page_is_mobile_first(self):
        r = self.client.get("/buddy/login")
        self.assertIn('name="viewport"', r.text)
        self.assertIn('type="password"', r.text)
        self.assertIn("noindex", r.text)

    # ── passcode exchange ────────────────────────────────────────────────

    def test_wrong_passcode_is_rejected_without_a_session(self):
        r = self.client.post("/buddy/api/login", json={"passcode": "not-it"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn(self.module.SESSION_COOKIE, r.cookies)

    def test_correct_passcode_issues_a_session_and_opens_the_dashboard(self):
        r = self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["redirect"], "/buddy")

        cookie = r.headers["set-cookie"]
        self.assertIn(self.module.SESSION_COOKIE, cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("samesite=lax", cookie.lower())

        dash = self.client.get("/buddy")
        self.assertEqual(dash.status_code, 200)
        # The existing Buddy dashboard, not a new one.
        self.assertIn('id="messages"', dash.text)
        self.assertIn("Talk to Buddy", dash.text)

    def test_master_token_is_also_accepted_as_break_glass_sign_in(self):
        r = self.client.post("/buddy/api/login", json={"passcode": TOKEN})
        self.assertEqual(r.status_code, 200)

    def test_form_encoded_login_works_for_browser_fallbacks(self):
        r = self.client.post("/buddy/api/login", data={"passcode": PASSCODE})
        self.assertEqual(r.status_code, 200)

    def test_session_cookie_never_carries_the_secret(self):
        r = self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        value = r.cookies[self.module.SESSION_COOKIE]
        self.assertNotIn(TOKEN, value)
        self.assertNotIn(PASSCODE, value)
        self.assertTrue(value.startswith("v1."))

    def test_session_survives_across_requests_for_daily_operations(self):
        self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        for path in ("/buddy", "/buddy/jobs", "/buddy"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_proposals_page_opens_on_the_same_session(self):
        self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        r = self.client.get("/buddy/jobs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Write Proposal", r.text)

    # ── session integrity ────────────────────────────────────────────────

    def test_forged_or_tampered_session_is_refused(self):
        good = self.module.issue_session()
        body, _, signature = good.rpartition(".")
        for bad in (
            "v1.9999999999.nonce.deadbeef",
            f"{body}.{'0' * len(signature)}",
            "garbage",
            "",
        ):
            client = TestClient(self.module.app, cookies={self.module.SESSION_COOKIE: bad})
            self.assertEqual(client.get("/buddy").status_code, 401)

    def test_expired_session_is_refused(self):
        stale = self.module.issue_session(now=time.time() - 10, ttl=5)
        self.assertFalse(self.module.session_is_valid(stale))
        client = TestClient(self.module.app, cookies={self.module.SESSION_COOKIE: stale})
        self.assertEqual(client.get("/buddy").status_code, 401)

    def test_rotating_the_master_token_invalidates_existing_sessions(self):
        stale = self.module.issue_session()
        rotated = load_app(token="rotated-token-1a2b3c4d5e6f7a8b9c0d")
        try:
            client = TestClient(rotated.app, cookies={rotated.SESSION_COOKIE: stale})
            self.assertEqual(client.get("/buddy").status_code, 401)
        finally:
            type(self).module = load_app()

    def test_signing_out_ends_the_session_on_this_device(self):
        self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        self.assertEqual(self.client.get("/buddy").status_code, 200)
        out = self.client.get("/buddy/logout", follow_redirects=False)
        self.assertEqual(out.status_code, 303)
        self.assertEqual(self.client.get("/buddy").status_code, 401)

    # ── brute force and credential hygiene ───────────────────────────────

    def test_repeated_failures_are_rate_limited(self):
        for _ in range(self.module.LOGIN_MAX_FAILURES):
            self.assertEqual(
                self.client.post("/buddy/api/login", json={"passcode": "wrong"}).status_code,
                401,
            )
        blocked = self.client.post("/buddy/api/login", json={"passcode": "wrong"})
        self.assertEqual(blocked.status_code, 429)
        # A correct passcode does not bypass the lockout window.
        self.assertEqual(
            self.client.post("/buddy/api/login", json={"passcode": PASSCODE}).status_code,
            429,
        )

    def test_successful_login_clears_the_failure_counter(self):
        self.client.post("/buddy/api/login", json={"passcode": "wrong"})
        self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        self.assertEqual(self.module._login_failures, {})

    def test_weak_passcode_is_refused_at_startup(self):
        weak = load_app(passcode="short")
        try:
            self.assertEqual(weak.BUDDY_PHONE_PASSCODE, "")
            client = TestClient(weak.app)
            self.assertEqual(
                client.post("/buddy/api/login", json={"passcode": "short"}).status_code, 401
            )
        finally:
            type(self).module = load_app()

    # ── machine callers keep working ─────────────────────────────────────

    def test_bearer_header_query_token_and_legacy_cookie_all_still_authenticate(self):
        self.assertEqual(
            self.client.get("/buddy", headers={"Authorization": f"Bearer {TOKEN}"}).status_code, 200
        )
        self.assertEqual(
            self.client.get("/buddy", headers={"X-Buddy-Token": TOKEN}).status_code, 200
        )
        self.assertEqual(self.client.get(f"/buddy?token={TOKEN}").status_code, 200)
        legacy = TestClient(self.module.app, cookies={"buddy_token": TOKEN})
        self.assertEqual(legacy.get("/buddy").status_code, 200)

    def test_token_in_the_url_is_upgraded_to_a_session_cookie(self):
        # So the secret only ever has to be pasted once, never bookmarked.
        r = self.client.get(f"/buddy?token={TOKEN}")
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.module.SESSION_COOKIE, r.headers.get("set-cookie", ""))

    def test_api_surfaces_answer_json_401_not_a_login_page(self):
        r = self.client.get("/buddy/api/status")
        self.assertEqual(r.status_code, 401)
        self.assertIn("application/json", r.headers["content-type"])

    def test_status_reports_auth_posture_without_secrets(self):
        self.client.post("/buddy/api/login", json={"passcode": PASSCODE})
        r = self.client.get("/buddy/api/status")
        self.assertEqual(r.status_code, 200)
        auth = r.json()["auth"]
        self.assertTrue(auth["phone_login"])
        self.assertTrue(auth["passcode_configured"])
        self.assertFalse(auth["token"]["conflict"])
        self.assertNotIn(TOKEN, r.text)
        self.assertNotIn(PASSCODE, r.text)

    def test_unconfigured_token_fails_closed_with_503(self):
        closed = load_app(token="", passcode="")
        try:
            client = TestClient(closed.app)
            self.assertEqual(client.get("/buddy").status_code, 503)
            self.assertEqual(client.post("/buddy/api/login", json={"passcode": "x"}).status_code, 503)
        finally:
            type(self).module = load_app()


if __name__ == "__main__":
    unittest.main()
