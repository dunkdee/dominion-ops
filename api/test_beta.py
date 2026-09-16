import os
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import beta
import vault_io


class CreatorBetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_root = vault_io.VAULT_ROOT
        vault_io.VAULT_ROOT = self.tmp.name
        os.environ["BETA_ALLOWED_ORIGINS"] = "https://dominionhealing.org"
        app = Flask(__name__)
        app.register_blueprint(beta.beta_bp)
        app.testing = True
        self.client = app.test_client()
        self.valid = {
            "name": "Beta Creator",
            "email": "creator@example.com",
            "creator_type": "solo_creator",
            "primary_platform": "multiple",
            "weekly_posts": 4,
            "biggest_pain": "time",
            "tried_last_7_days": True,
            "consent": True,
            "website": "",
            "source": "youtube",
        }

    def tearDown(self):
        vault_io.VAULT_ROOT = self.previous_root
        self.tmp.cleanup()

    def post(self, payload=None, origin="https://dominionhealing.org"):
        return self.client.post(
            "/beta/apply",
            json=payload or self.valid,
            headers={"Origin": origin},
        )

    def test_valid_application_writes_receipt_and_scores_priority(self):
        response = self.post()
        body = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(body["accepted"])
        self.assertEqual(body["status"], "priority_review")
        self.assertTrue(body["application_id"].startswith("beta_"))
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "https://dominionhealing.org")
        notes = vault_io.list_lane("beta")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["application_id"], body["application_id"])
        self.assertEqual(notes[0]["qualification_score"], 7)
        self.assertTrue(notes[0]["consent"])

    def test_duplicate_email_returns_original_receipt(self):
        first = self.post().get_json()
        second_response = self.post()
        second = second_response.get_json()
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second["status"], "already_received")
        self.assertEqual(second["application_id"], first["application_id"])
        self.assertEqual(len(vault_io.list_lane("beta")), 1)

    def test_missing_consent_fails_closed(self):
        payload = dict(self.valid, consent=False)
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "consent_required")
        self.assertEqual(len(vault_io.list_lane("beta")), 0)

    def test_disallowed_origin_gets_no_cors_grant(self):
        response = self.post(origin="https://evil.example")
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_honeypot_does_not_write_vault(self):
        payload = dict(self.valid, website="spam.example")
        response = self.post(payload)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(vault_io.list_lane("beta")), 0)


if __name__ == "__main__":
    unittest.main()
