from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from apps.dominion_publisher.adapters.meta import MetaInstagramAdapter
from apps.dominion_publisher.meta_binding import META_SCOPES, MetaBindingManager
from apps.dominion_publisher.models import Asset, PublishJob, utc_now
from apps.dominion_publisher.vault import CredentialVault


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._data


class FakeGetSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)

    def post(self, url: str, data: dict, timeout: int) -> FakeResponse:
        self.post_calls.append({"url": url, "data": data, "timeout": timeout})
        return self.responses.pop(0)


class FakePostSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url: str, data: dict, timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        return self.responses.pop(0)


def configured_vault(tmp_path) -> CredentialVault:
    vault = CredentialVault(tmp_path / "vault")
    vault.configure_meta_app(
        app_id="123456789",
        app_secret="meta-super-secret",
        redirect_uri="https://dominionhealing.org/oauth/meta/callback",
        graph_version="v25.0",
    )
    return vault


def test_vault_encrypts_meta_secret_at_rest(tmp_path):
    vault = configured_vault(tmp_path)

    ciphertext = vault.data_path.read_bytes()

    assert b"meta-super-secret" not in ciphertext
    assert b"123456789" not in ciphertext
    assert vault.data_path.stat().st_mode & 0o777 == 0o600
    assert vault.key_path.stat().st_mode & 0o777 == 0o600


def test_authorization_url_requests_required_publish_scopes(tmp_path):
    vault = configured_vault(tmp_path)
    manager = MetaBindingManager(vault)

    url = manager.authorization_url()
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "www.facebook.com"
    assert parsed.path.endswith("/dialog/oauth")
    assert query["client_id"] == ["123456789"]
    assert query["redirect_uri"] == ["https://dominionhealing.org/oauth/meta/callback"]
    assert set(query["scope"][0].split(",")) == set(META_SCOPES)
    assert query["state"][0]


def test_callback_discovers_and_binds_page_and_instagram_without_exposing_token(tmp_path):
    vault = configured_vault(tmp_path)
    session = FakeGetSession(
        [
            FakeResponse({"access_token": "short-user-token"}),
            FakeResponse({"access_token": "long-user-token"}),
            FakeResponse(
                {
                    "data": [
                        {
                            "id": "fb-page-1",
                            "name": "VoltEdge",
                            "access_token": "page-secret-token",
                            "tasks": ["ANALYZE", "CREATE_CONTENT", "MODERATE"],
                            "instagram_business_account": {"id": "ig-professional-1"},
                        }
                    ]
                }
            ),
        ]
    )
    manager = MetaBindingManager(vault, session=session)
    state = parse_qs(urlsplit(manager.authorization_url()).query)["state"][0]

    candidates = manager.complete_callback(code="oauth-code", state=state)

    assert candidates == [
        {
            "page_id": "fb-page-1",
            "page_name": "VoltEdge",
            "instagram_account_id": "ig-professional-1",
            "tasks": ["ANALYZE", "CREATE_CONTENT", "MODERATE"],
        }
    ]
    assert session.calls[0] == {
        "url": "https://graph.facebook.com/v25.0/oauth/access_token",
        "params": {
            "client_id": "123456789",
            "redirect_uri": "https://dominionhealing.org/oauth/meta/callback",
            "client_secret": "meta-super-secret",
            "code": "oauth-code",
        },
        "timeout": 30,
    }
    assert "grant_type" not in session.calls[0]["params"]
    assert "code_verifier" not in session.calls[0]["params"]
    assert session.post_calls == []
    assert "page-secret-token" not in repr(candidates)
    binding = vault.bind_page(page_id="fb-page-1", approved_by="founder")
    assert binding["facebook"]["account_id"] == "fb-page-1"
    assert binding["instagram"]["account_id"] == "ig-professional-1"
    assert vault.token_for("facebook", "fb-page-1") == "page-secret-token"
    assert vault.token_for("instagram", "ig-professional-1") == "page-secret-token"
    assert "page-secret-token" not in repr(vault.bound_accounts_safe())


def test_oauth_state_is_one_time(tmp_path):
    vault = configured_vault(tmp_path)
    session = FakeGetSession(
        [
            FakeResponse({"access_token": "short"}),
            FakeResponse({"access_token": "long"}),
            FakeResponse(
                {
                    "data": [
                        {
                            "id": "page",
                            "name": "VoltEdge",
                            "access_token": "page-token",
                            "tasks": ["CREATE_CONTENT"],
                        }
                    ]
                }
            ),
        ]
    )
    manager = MetaBindingManager(vault, session=session)
    state = parse_qs(urlsplit(manager.authorization_url()).query)["state"][0]
    manager.complete_callback(code="first-code", state=state)

    with pytest.raises(PermissionError, match="already consumed"):
        manager.complete_callback(code="second-code", state=state)


def test_bound_account_token_resolver_drives_instagram_publish(tmp_path):
    vault = configured_vault(tmp_path)
    vault.set_pending_meta(
        candidates=[
            {
                "page_id": "page-1",
                "page_name": "VoltEdge",
                "page_access_token": "encrypted-page-token",
                "instagram_account_id": "ig-1",
                "tasks": ["CREATE_CONTENT"],
            }
        ],
        expires_at="2999-01-01T00:00:00+00:00",
    )
    vault.bind_page(page_id="page-1", approved_by="founder")
    session = FakePostSession([FakeResponse({"id": "container-1"}), FakeResponse({"id": "post-1"})])
    adapter = MetaInstagramAdapter(
        token_resolver=vault.token_for,
        version_resolver=vault.graph_version,
        session=session,
    )
    job = PublishJob(
        campaign_id="voltedge-canary",
        platform="instagram",
        account_id="ig-1",
        caption="VoltEdge canary",
        destination_url="https://www.voltedgegoods.com/",
        assets=[
            Asset(
                uri="https://cdn.example.com/owned.jpg",
                sha256="a" * 64,
                provenance="owned-product-catalog",
                media_type="image/jpeg",
            )
        ],
        approved_by="founder",
        approved_at=utc_now(),
    )

    post_id = adapter.publish(job)

    assert post_id == "post-1"
    assert session.calls[0]["data"]["access_token"] == "encrypted-page-token"
    assert session.calls[1]["data"]["access_token"] == "encrypted-page-token"
