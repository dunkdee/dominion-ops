"""Final regression for Founder approval authentication on PR #235."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from buddy_core import buddy_web


class FounderApprovalAuthBoundaryTests(unittest.TestCase):
    def _request(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={},
            query_params={},
            cookies={},
        )

    def test_open_dev_cannot_substitute_for_founder_authentication(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", ""), \
             mock.patch.object(buddy_web, "BUDDY_ALLOW_OPEN_DEV", True):
            # Ordinary dev access may pass on loopback...
            self.assertIsNone(buddy_web.verify_token(request))
            # ...but authority mutation must still fail closed.
            with self.assertRaises(HTTPException) as ctx:
                buddy_web.verify_founder_authority(request)
            self.assertEqual(ctx.exception.status_code, 503)

    def test_configured_token_still_requires_authenticated_request(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", "configured-secret"), \
             mock.patch.object(buddy_web, "is_authenticated", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                buddy_web.verify_founder_authority(request)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_authenticated_request_is_allowed_to_reach_authority_layer(self):
        request = self._request()
        with mock.patch.object(buddy_web, "BUDDY_WEB_TOKEN", "configured-secret"), \
             mock.patch.object(buddy_web, "is_authenticated", return_value=True):
            self.assertIsNone(buddy_web.verify_founder_authority(request))


if __name__ == "__main__":
    unittest.main()
