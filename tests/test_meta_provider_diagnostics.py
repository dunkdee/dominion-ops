from __future__ import annotations

import pytest
import requests
import traceback
from types import SimpleNamespace

from apps.dominion_publisher.meta_binding import MetaBindingManager


class FakeErrorResponse:
    ok = False
    status_code = 400

    def json(self) -> dict:
        return {
            "error": {
                "message": "Secret-bearing provider text must never be reflected: oauth-code app-secret token-value",
                "type": "OAuthException",
                "code": 100,
                "error_subcode": 36008,
                "fbtrace_id": "safe-trace-id",
            }
        }


def test_provider_error_exposes_only_allowlisted_diagnostics() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        MetaBindingManager._provider_json(FakeErrorResponse(), "authorization-code exchange")

    message = str(exc_info.value)
    assert message == (
        "Meta authorization-code exchange failed with HTTP 400 "
        "(type=OAuthException, code=100, error_subcode=36008)"
    )
    assert "oauth-code" not in message
    assert "app-secret" not in message
    assert "token-value" not in message
    assert "fbtrace_id" not in message
    assert "safe-trace-id" not in message


class FakeNonJsonErrorResponse:
    ok = False
    status_code = 502

    def json(self) -> dict:
        raise ValueError("not json")


def test_provider_non_json_error_stays_generic() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        MetaBindingManager._provider_json(FakeNonJsonErrorResponse(), "authorization-code exchange")

    assert str(exc_info.value) == "Meta authorization-code exchange failed with HTTP 502"


@pytest.mark.parametrize("value", [
    {"secret": "REDACTION_CANARY"}, ["REDACTION_CANARY"],
    "REDACTION_CANARY", "OAuthException\nREDACTION_CANARY", None, True,
])
def test_provider_rejects_arbitrary_error_type(value):
    response = SimpleNamespace(ok=False, status_code=400, json=lambda: {
        "error": {"type": value, "message": "REDACTION_CANARY", "fbtrace_id": "REDACTION_CANARY"}
    })
    with pytest.raises(RuntimeError) as exc:
        MetaBindingManager._provider_json(response, "authorization-code exchange")
    assert str(exc.value) == "Meta authorization-code exchange failed with HTTP 400"


@pytest.mark.parametrize("value", [True, -1, 2**31, "9" * 1000, "١٢", "12\n", {}, []])
def test_provider_rejects_malformed_numeric_diagnostics(value):
    response = SimpleNamespace(ok=False, status_code=400, json=lambda: {
        "error": {"code": value, "error_subcode": value}
    })
    with pytest.raises(RuntimeError) as exc:
        MetaBindingManager._provider_json(response, "managed-Page discovery")
    assert str(exc.value) == "Meta managed-Page discovery failed with HTTP 400"


def test_provider_normalizes_decimal_codes():
    response = SimpleNamespace(ok=False, status_code=400, json=lambda: {
        "error": {"code": "00100", "error_subcode": "36008"}
    })
    with pytest.raises(RuntimeError, match=r"\(code=100, error_subcode=36008\)$"):
        MetaBindingManager._provider_json(response, "managed-Page discovery")


def test_success_json_decode_failure_does_not_expose_exception():
    def bad_json():
        raise ValueError("REDACTION_CANARY")
    response = SimpleNamespace(ok=True, json=bad_json)
    with pytest.raises(RuntimeError) as exc:
        MetaBindingManager._provider_json(response, "authorization-code exchange")
    assert str(exc.value) == "Meta authorization-code exchange returned an invalid response"
    assert "REDACTION_CANARY" not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("exception_class", [requests.Timeout, requests.ConnectionError, requests.TooManyRedirects])
@pytest.mark.parametrize("failure_stage,operation", [
    (0, "authorization-code exchange"), (1, "long-lived token exchange"),
    (2, "managed-Page discovery"),
])
def test_each_oauth_request_redacts_transport_errors(exception_class, failure_stage, operation):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if len(calls) - 1 == failure_stage:
            raise exception_class("https://graph.facebook.com/?client_secret=REDACTION_CANARY")
        return SimpleNamespace(ok=True, json=lambda: {"access_token": "synthetic-token"})
    vault = SimpleNamespace(meta_app=lambda: {
        "app_id": "test-id", "app_secret": "synthetic-secret",
        "graph_version": "v25.0", "redirect_uri": "https://example.invalid/callback",
    })
    manager = MetaBindingManager(vault, session=SimpleNamespace(get=get))
    with pytest.raises(RuntimeError) as exc:
        token = manager._exchange_code("synthetic-code")
        manager._discover_pages(token)
    assert str(exc.value) == f"Meta {operation} failed with a transport error"
    assert len(calls) == failure_stage + 1
    assert "REDACTION_CANARY" not in "".join(traceback.format_exception(exc.value))
