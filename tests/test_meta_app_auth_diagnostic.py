"""Exercise the actual workflow Python without VM access or provider requests."""

from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest
import requests

from apps.dominion_publisher import vault


@pytest.fixture
def diagnose(monkeypatch, capsys):
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/diagnose-meta-app-auth.yml"
    text = workflow.read_text()
    code = dedent(text.split('"$venv/bin/python" - <<\'PY\'\n', 1)[1].split("          PY\n", 1)[0])
    monkeypatch.setenv("DOMINION_PUBLISHER_VAULT", "/synthetic/vault")

    def run(payload=None, status=400, request_error=None, json_error=None, vault_error=None, version="v25.0"):
        app = {"app_id": "synthetic-id", "app_secret": "REDACTION_CANARY", "graph_version": version}
        def read_app():
            if vault_error:
                raise vault_error
            return app
        monkeypatch.setattr(vault, "CredentialVault", lambda root: SimpleNamespace(meta_app=read_app))
        calls = []
        def get(url, **kwargs):
            calls.append((url, kwargs))
            assert kwargs["allow_redirects"] is False
            assert kwargs["timeout"] == 30
            if request_error:
                raise request_error
            def decode():
                if json_error:
                    raise json_error
                return payload
            return SimpleNamespace(status_code=status, ok=status < 400, json=decode)
        monkeypatch.setattr(requests, "get", get)
        with pytest.raises(SystemExit) as exc:
            exec(compile(code, str(workflow), "exec"), {})
        output = capsys.readouterr()
        assert output.err == ""
        assert "REDACTION_CANARY" not in output.out
        assert "synthetic-id" not in output.out
        return exc.value.code, output.out, calls
    return run


@pytest.mark.parametrize("value", [
    {"secret": "REDACTION_CANARY"}, ["REDACTION_CANARY"],
    "REDACTION_CANARY", "OAuthException\nREDACTION_CANARY", None, True,
])
def test_arbitrary_provider_fields_are_never_printed(diagnose, value):
    code, output, _ = diagnose({"error": {
        "type": value, "message": "REDACTION_CANARY", "fbtrace_id": "REDACTION_CANARY",
    }})
    assert code == 26
    assert output == "META_APP_AUTH=FAIL http_status=400\n"


@pytest.mark.parametrize("value", [True, -1, 2**31, "9" * 1000, "١٢", "12\n", {}, []])
def test_malformed_numeric_codes_are_omitted(diagnose, value):
    code, output, _ = diagnose({"error": {"code": value, "error_subcode": value}})
    assert code == 26
    assert output == "META_APP_AUTH=FAIL http_status=400\n"


def test_known_diagnostics_remain_useful(diagnose):
    code, output, _ = diagnose({"error": {
        "type": "OAuthException", "code": "00100", "error_subcode": 36008,
        "message": "REDACTION_CANARY", "fbtrace_id": "REDACTION_CANARY",
    }})
    assert code == 26
    assert output == "META_APP_AUTH=FAIL http_status=400 (type=OAuthException, code=100, error_subcode=36008)\n"


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError, requests.TooManyRedirects])
def test_request_failures_exit_cleanly_without_exception_text(diagnose, error):
    code, output, calls = diagnose(request_error=error("URL?client_secret=REDACTION_CANARY"))
    assert code == 29
    assert output == "META_APP_AUTH=FAIL reason=transport_error\n"
    assert len(calls) == 1


@pytest.mark.parametrize("status", [200, 400, 502])
def test_non_json_response_stays_redacted(diagnose, status):
    code, output, _ = diagnose(status=status, json_error=ValueError("REDACTION_CANARY"))
    assert code == (25 if status == 200 else 26)
    assert "META_APP_AUTH=FAIL" in output


@pytest.mark.parametrize("token", [None, {}, ["REDACTION_CANARY"], True, 123, "", "   "])
def test_success_requires_nonempty_string_token(diagnose, token):
    code, output, _ = diagnose({"access_token": token}, status=200)
    assert code == 25
    assert output == "META_APP_AUTH=FAIL reason=success_without_access_token\n"


def test_valid_token_passes_without_printing_it(diagnose):
    code, output, _ = diagnose({"access_token": "REDACTION_CANARY"}, status=200)
    assert code == 0
    assert output == "META_APP_AUTH=PASS\nGRAPH_VERSION=v25.0\n"


def test_redirect_is_not_accepted_as_authentication(diagnose):
    code, output, _ = diagnose({"access_token": "REDACTION_CANARY"}, status=302)
    assert code == 26
    assert output == "META_APP_AUTH=FAIL http_status=302\n"


@pytest.mark.parametrize("error", [OSError, ValueError, RuntimeError])
def test_vault_errors_are_redacted_before_any_request(diagnose, error):
    code, output, calls = diagnose(vault_error=error("REDACTION_CANARY"))
    assert code == 27
    assert output == "META_APP_AUTH=FAIL reason=vault_read_failed\n"
    assert calls == []


def test_invalid_graph_version_cannot_enter_url_or_output(diagnose):
    code, output, calls = diagnose(version="v25.0?REDACTION_CANARY")
    assert code == 28
    assert output == "META_APP_AUTH=FAIL reason=invalid_graph_version\n"
    assert calls == []
