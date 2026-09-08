"""Facebook Login for Business apps need a config_id, not a scope list.

The Meta app behind the Publisher is a Facebook Login for Business app. That
product draws its permissions from a saved configuration and refuses a classic
scope request -- it answers with "It looks like this app isn't available. This
app needs at least one supported permission" no matter how many permissions are
enabled on the app. Requesting consent with `scope=` therefore could never
succeed, and the fix is to send `config_id` instead.

Apps on classic Facebook Login must keep working unchanged, so the config_id is
optional and its absence preserves the scope flow exactly.

These tests drive authorization_url() against a stub vault: no cryptography, no
network, no real credentials.
"""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from apps.dominion_publisher.meta_binding import META_SCOPES, MetaBindingManager

APP_ID = "1948190132729403"
CONFIG_ID = "2114196859524400"
REDIRECT_URI = "https://example.invalid/oauth/meta/callback"


class _StubVault:
    """Only the surface authorization_url() touches."""

    def __init__(self, **overrides):
        self._app = {
            "app_id": APP_ID,
            "app_secret": "not-a-real-secret",
            "redirect_uri": REDIRECT_URI,
            "graph_version": "v25.0",
            **overrides,
        }

    def meta_app(self):
        return dict(self._app)

    def state_secret(self):
        return b"state-secret-for-tests"


def _params(url: str) -> dict:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


class BusinessLoginTests(unittest.TestCase):
    def url(self, **overrides) -> str:
        return MetaBindingManager(_StubVault(**overrides)).authorization_url()

    def test_config_id_is_sent_when_configured(self):
        self.assertEqual(_params(self.url(config_id=CONFIG_ID))["config_id"], CONFIG_ID)

    def test_scope_is_omitted_when_a_config_id_is_configured(self):
        """The regression itself: scope and config_id must never travel together."""
        self.assertNotIn("scope", _params(self.url(config_id=CONFIG_ID)))

    def test_state_and_redirect_still_travel_on_the_business_flow(self):
        params = _params(self.url(config_id=CONFIG_ID))
        self.assertEqual(params["redirect_uri"], REDIRECT_URI)
        self.assertEqual(params["client_id"], APP_ID)
        self.assertEqual(params["response_type"], "code")
        self.assertIn(".", params["state"], "state must remain the signed payload.signature")

    def test_blank_or_whitespace_config_id_falls_back_to_classic_login(self):
        for value in ("", "   "):
            with self.subTest(config_id=repr(value)):
                params = _params(self.url(config_id=value))
                self.assertNotIn("config_id", params)
                self.assertEqual(params["scope"], ",".join(META_SCOPES))


class ClassicLoginUnchangedTests(unittest.TestCase):
    """A vault written before config_id existed has no such key at all."""

    def test_absent_key_keeps_the_scope_flow(self):
        url = MetaBindingManager(_StubVault()).authorization_url()
        params = _params(url)
        self.assertNotIn("config_id", params)
        self.assertEqual(params["scope"], ",".join(META_SCOPES))

    def test_dialog_endpoint_is_unchanged_on_both_flows(self):
        for overrides in ({}, {"config_id": CONFIG_ID}):
            with self.subTest(overrides=overrides):
                url = MetaBindingManager(_StubVault(**overrides)).authorization_url()
                self.assertTrue(
                    url.startswith("https://www.facebook.com/v25.0/dialog/oauth?"), url
                )


class StatePreservedAcrossFlowsTests(unittest.TestCase):
    def test_each_call_mints_a_distinct_state(self):
        manager = MetaBindingManager(_StubVault(config_id=CONFIG_ID))
        first = _params(manager.authorization_url())["state"]
        second = _params(manager.authorization_url())["state"]
        self.assertNotEqual(first, second, "state must be single-use, not reused")


if __name__ == "__main__":
    unittest.main()
