"""Secret redaction (Gate 8, rule 8).

Two properties are tested separately because they fail differently:

  known values  a secret this process holds must never render
  shapes        a secret we never held must still be caught on sight

The second is the one that matters in practice -- a key pasted into a task
objective was never in our config, so only shape matching can catch it.
"""

from __future__ import annotations

import json
import logging

from apps.council_node.app.logging import (
    REDACTED, RedactingJSONFormatter, redact, redact_structure,
)

OPENAI_KEY = "sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"
GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SLACK_TOKEN = "xoxb-1111111111-2222222222-abcdefghijkl"
DB_URL = "postgresql://dominion:supersecretpassword@db.internal:5432/council"


def test_known_value_is_removed():
    secret = "a-configured-founder-token-value"
    assert secret not in redact(f"token={secret}", (secret,))


def test_short_values_are_not_over_redacted():
    """A 3-char value must not blank out unrelated text."""
    assert redact("the cat sat on the mat", ("cat",)) == "the cat sat on the mat"


def test_openai_key_shape_is_caught_without_configuration():
    out = redact(f"calling with {OPENAI_KEY}")
    assert OPENAI_KEY not in out
    assert REDACTED in out


def test_github_and_slack_token_shapes_are_caught():
    for token in (GITHUB_TOKEN, SLACK_TOKEN):
        out = redact(f"authorization: {token}")
        assert token not in out


def test_connection_url_password_is_stripped_but_host_survives():
    out = redact(DB_URL)
    assert "supersecretpassword" not in out
    assert "db.internal" in out, "the host is diagnostic and should survive"


def test_authorization_header_is_redacted():
    out = redact("Authorization: Bearer abcdef123456789")
    assert "abcdef123456789" not in out


def test_structure_redaction_uses_key_names():
    """A value with no recognisable shape is still caught by its key name."""
    payload = {
        "user": "dewayne",
        "api_key": "plain-looking-but-secret",
        "nested": {"founder_token": "another-one", "safe": "keep me"},
        "items": ["ordinary", {"password": "hunter2"}],
    }
    out = redact_structure(payload)
    assert out["api_key"] == REDACTED
    assert out["nested"]["founder_token"] == REDACTED
    assert out["items"][1]["password"] == REDACTED
    assert out["user"] == "dewayne"
    assert out["nested"]["safe"] == "keep me"


def test_log_formatter_redacts_message_and_fields():
    formatter = RedactingJSONFormatter(secret_values=("configured-secret-value",))
    record = logging.LogRecord(
        name="council.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="using %s and %s", args=("configured-secret-value", OPENAI_KEY), exc_info=None,
    )
    record.task_id = "t-1"
    payload = json.loads(formatter.format(record))
    assert "configured-secret-value" not in payload["message"]
    assert OPENAI_KEY not in payload["message"]
    assert payload["task_id"] == "t-1"


def test_exception_text_is_redacted():
    formatter = RedactingJSONFormatter()
    try:
        raise ValueError(f"failed calling {OPENAI_KEY}")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="council.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="boom", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(formatter.format(record))
    assert OPENAI_KEY not in payload["exception"]
