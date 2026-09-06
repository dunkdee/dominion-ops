"""meta_control.sh must show the operator why the API refused.

The script used `curl -fsS`, which throws away the response body on an HTTP
error. A real 503 carrying "Meta app configuration is not present in the
encrypted vault" reached the operator as nothing but
`curl: (22) The requested URL returned error: 503` -- the diagnosis existed and
was discarded.

These tests run the real script against a stub HTTP server. No cryptography, no
Publisher runtime, no network beyond loopback.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dominion_publisher" / "meta_control.sh"

ERROR_DETAIL = "Meta app configuration is not present in the encrypted vault"
OPERATOR_TOKEN = "test-operator-token-not-a-real-secret"


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 503
    payload = {"detail": ERROR_DETAIL}

    def _respond(self):
        # Record whether the operator token was presented as a header.
        type(self).seen_token = self.headers.get("X-Operator-Token")
        body = json.dumps(type(self).payload).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _respond
    do_POST = _respond

    def log_message(self, *args):  # keep test output clean
        pass


class MetaControlErrorReportingTests(unittest.TestCase):
    def setUp(self):
        _Handler.status = 503
        _Handler.payload = {"detail": ERROR_DETAIL}
        _Handler.seen_token = None

        self.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        state = Path(self._tmp.name)
        (state / "venv" / "bin").mkdir(parents=True)
        # require_runtime only checks that this is executable.
        python_stub = state / "venv" / "bin" / "python"
        python_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python_stub.chmod(0o700)
        (state / "runtime.env").write_text(
            f"DOMINION_PUBLISHER_OPERATOR_TOKEN={OPERATOR_TOKEN}\n", encoding="utf-8"
        )
        self.state = state

    def run_control(self, *args):
        env = dict(os.environ)
        env["DOMINION_PUBLISHER_STATE_ROOT"] = str(self.state)
        env["DOMINION_PUBLISHER_LOCAL_URL"] = f"http://127.0.0.1:{self.port}"
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, env=env, timeout=60,
        )

    # ── the defect ───────────────────────────────────────────────────────

    def test_start_surfaces_the_server_error_message(self):
        result = self.run_control("start")
        combined = result.stdout + result.stderr
        self.assertIn(ERROR_DETAIL, combined,
                      "the server's explanation must reach the operator")

    def test_start_reports_the_http_status(self):
        result = self.run_control("start")
        self.assertIn("http_status=503", result.stdout + result.stderr)

    def test_failure_exit_code_is_preserved(self):
        self.assertEqual(self.run_control("start").returncode, 22)

    def test_candidates_and_accounts_also_surface_the_error(self):
        for action in ("candidates", "accounts"):
            with self.subTest(action=action):
                result = self.run_control(action)
                self.assertIn(ERROR_DETAIL, result.stdout + result.stderr)
                self.assertEqual(result.returncode, 22)

    def test_bind_surfaces_the_error(self):
        result = self.run_control("bind", "123456789", "founder")
        self.assertIn(ERROR_DETAIL, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 22)

    # ── success path still works ─────────────────────────────────────────

    def test_successful_start_prints_the_authorization_url(self):
        _Handler.status = 200
        _Handler.payload = {
            "authorization_url": "https://www.facebook.com/v25.0/dialog/oauth?client_id=x",
            "expires_in_seconds": 600,
        }
        result = self.run_control("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("META_BINDING_START=PASS", result.stdout)
        self.assertIn("AUTHORIZATION_URL=https://www.facebook.com/", result.stdout)

    def test_successful_candidates_returns_json(self):
        _Handler.status = 200
        _Handler.payload = {"candidates": []}
        result = self.run_control("candidates")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("candidates", result.stdout)

    # ── the token is a header, never output ──────────────────────────────

    def test_operator_token_is_sent_as_a_header_and_never_printed(self):
        result = self.run_control("start")
        self.assertEqual(_Handler.seen_token, OPERATOR_TOKEN,
                         "the token must still authenticate the request")
        self.assertNotIn(OPERATOR_TOKEN, result.stdout + result.stderr,
                         "the token must never appear in output")


if __name__ == "__main__":
    unittest.main()
