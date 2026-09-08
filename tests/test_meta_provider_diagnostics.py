from __future__ import annotations

import pytest

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


class FakeNonJsonErrorResponse:
    ok = False
    status_code = 502

    def json(self) -> dict:
        raise ValueError("not json")


def test_provider_non_json_error_stays_generic() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        MetaBindingManager._provider_json(FakeNonJsonErrorResponse(), "authorization-code exchange")

    assert str(exc_info.value) == "Meta authorization-code exchange failed with HTTP 502"
