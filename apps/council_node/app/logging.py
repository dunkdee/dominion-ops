"""Structured logging with mandatory secret redaction.

Governance rule 8: no secret may appear in logs, Git history, prompts,
screenshots, or receipts. This module is the single chokepoint for that rule
on the logging side, and `redact()` is reused by the model router so an
outbound prompt is filtered by exactly the same code that filters a log line.

The redactor works on two levels:

  known values   every secret the process actually holds (from Settings)
  shaped tokens  provider key formats that are recognisable on sight, so a
                 secret that was never in our config -- pasted by a user,
                 echoed by an API -- is still caught

Shape matching is deliberately conservative. It targets formats that are
unambiguous (``sk-``-prefixed keys, bearer headers, connection URLs with
inline credentials) rather than anything long and random, because
over-redaction destroys the diagnostic value of a log.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any, Iterable

REDACTED = "[REDACTED]"

# Formats worth catching on shape alone, each paired with its own
# replacement. Pairing matters: an earlier version chose the replacement by
# whether a pattern happened to have a capture group, which silently applied
# the connection-URL rewrite to the Authorization header and left the token
# after "Bearer" in the clear.
_SHAPE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # OpenAI / Anthropic style keys.
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b"), REDACTED),
    (re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_\-]{16,}\b"), REDACTED),
    # GitHub tokens.
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), REDACTED),
    # Slack.
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), REDACTED),
    # Private key blocks.
    (re.compile(r"(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"),
     REDACTED),
    # Credential-bearing headers. The whole remainder of the line goes, so a
    # "Bearer <token>" pair cannot leave its second half behind.
    (re.compile(r"(?i)\b(authorization|x-operator-token|x-founder-token|x-api-key)\s*[:=]\s*\S.*"),
     r"\1: " + REDACTED),
    # Credentials embedded in a connection URL: scheme://user:secret@host
    (re.compile(r"\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):[^\s@]+@"), r"\1:" + REDACTED + "@"),
)


def redact(text: str, extra_values: Iterable[str] = ()) -> str:
    """Remove known secret values and recognisable secret shapes from text."""
    if not text:
        return text

    for value in extra_values:
        if value and len(value) >= 8 and value in text:
            text = text.replace(value, REDACTED)

    for pattern, replacement in _SHAPE_RULES:
        text = pattern.sub(replacement, text)
    return text


def redact_structure(value: Any, extra_values: Iterable[str] = ()) -> Any:
    """Redact recursively through dicts, lists and strings.

    A key whose name looks secret has its whole value replaced, because the
    value may be a secret that matches no shape at all.
    """
    from .config import SECRET_ENV_SUFFIXES

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            name = str(key).upper()
            if any(name.endswith(s) or s in name for s in SECRET_ENV_SUFFIXES):
                out[key] = REDACTED
            else:
                out[key] = redact_structure(item, extra_values)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_structure(v, extra_values) for v in value]
    if isinstance(value, str):
        return redact(value, extra_values)
    return value


class RedactingJSONFormatter(logging.Formatter):
    """Emits one JSON object per line, with every field redacted."""

    def __init__(self, secret_values: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secret_values)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage(), self._secrets),
        }
        for field in ("trace_id", "task_id", "lane_id", "agent_id", "receipt_id"):
            found = getattr(record, field, None)
            if found is not None:
                payload[field] = redact(str(found), self._secrets)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info), self._secrets)
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: str = "INFO", secret_values: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingJSONFormatter(secret_values))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"council.{name}")
