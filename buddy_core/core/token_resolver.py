"""
BUDDY_WEB_TOKEN resolution — one deterministic source of truth.
==============================================================

Buddy's auth secret historically lived in three dotenv files plus the systemd
service environment:

    process environment          (systemd Environment= / EnvironmentFile=)
    ~/buddy_core/.env
    ~/conductor/.env
    ~/.env

Every consumer re-implemented its own discovery, and the sentinel appended a
second ``BUDDY_WEB_TOKEN=`` line whenever a file held an empty one. Two
concrete failures came out of that:

1.  A file could end up with duplicate assignments. ``python-dotenv`` with
    ``override=False`` keeps the FIRST assignment it sees, so an empty
    ``BUDDY_WEB_TOKEN=`` line shadowed the real value below it and Buddy
    answered HTTP 503 "authentication is not configured".
2.  Two files could hold different non-empty tokens. Nothing detected it, so
    Buddy Web, the bridge and the Command Center could each authenticate with a
    different secret depending on which discovery order ran.

This module is the only place that answers "what is the token?". Resolution is
explicit and identical for every caller:

*   Highest precedence first, first NON-EMPTY value wins.
*   Within a single file the LAST assignment wins (``source``/shell semantics),
    so an appended repair line takes effect instead of being shadowed.
*   Disagreement between sources is reported, never silently picked.

Nothing here ever logs, prints or returns the secret itself. Conflict
diagnostics use a truncated SHA-256 fingerprint so two values can be compared
without either being disclosed.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

TOKEN_KEY = "BUDDY_WEB_TOKEN"

PROCESS_ENV_SOURCE = "process-environment"

# Highest precedence first. Mirrors the historical buddy_web.py load order so
# the resolved token does not change on any correctly configured host.
ENV_FILE_ORDER = (
    ("buddy_core/.env", Path("buddy_core") / ".env"),
    ("conductor/.env", Path("conductor") / ".env"),
    ("~/.env", Path(".env")),
)


def fingerprint(value: str) -> str:
    """Short, non-reversible identity for a secret. Never the secret itself."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def parse_env_file(path: Path) -> dict:
    """Parse a dotenv file with shell ``source`` semantics: last write wins.

    Deliberately tolerant — this reads operator-maintained files, not a strict
    format. Unreadable files resolve to an empty mapping rather than raising,
    because a missing sidecar file must never take Buddy's auth offline.
    """
    values: dict = {}
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return values
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        # Last assignment wins, matching `source file` and unlike
        # load_dotenv(override=False), which kept the first (often empty) one.
        values[key] = value
    return values


def count_assignments(path: Path, key: str = TOKEN_KEY) -> int:
    """How many times ``key`` is assigned in ``path``. >1 means a duplicate."""
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    total = 0
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if line.partition("=")[0].strip() == key:
            total += 1
    return total


@dataclass
class TokenResolution:
    """The resolved token plus everything needed to explain the choice."""

    token: str = ""
    source: str = ""
    candidates: list = field(default_factory=list)   # [{source, fingerprint}]
    conflicting_sources: list = field(default_factory=list)
    duplicate_sources: list = field(default_factory=list)
    empty_sources: list = field(default_factory=list)

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def conflict(self) -> bool:
        """True when two sources hold different non-empty tokens."""
        return len(self.conflicting_sources) > 1

    @property
    def duplicated(self) -> bool:
        """True when any single file assigns the token more than once."""
        return bool(self.duplicate_sources)

    def report(self) -> dict:
        """Operator-facing summary. Contains no secret material."""
        return {
            "configured": self.configured,
            "source": self.source,
            "conflict": self.conflict,
            "conflicting_sources": list(self.conflicting_sources),
            "duplicate_sources": list(self.duplicate_sources),
            "empty_sources": list(self.empty_sources),
            "candidate_sources": [c["source"] for c in self.candidates],
        }


def env_file_paths(home: Path | None = None) -> list:
    base = Path(home) if home is not None else Path.home()
    return [(label, base / rel) for label, rel in ENV_FILE_ORDER]


def resolve_buddy_web_token(
    env: Mapping | None = None,
    home: Path | None = None,
    key: str = TOKEN_KEY,
    extra_files: Iterable | None = None,
) -> TokenResolution:
    """Resolve ``BUDDY_WEB_TOKEN`` deterministically across every source."""
    env = os.environ if env is None else env
    resolution = TokenResolution()

    ordered = []
    process_value = str(env.get(key, "") or "").strip()
    ordered.append((PROCESS_ENV_SOURCE, process_value, None))

    files = env_file_paths(home)
    if extra_files:
        files = files + [(str(p), Path(p)) for p in extra_files]

    for label, path in files:
        parsed = parse_env_file(path)
        ordered.append((label, str(parsed.get(key, "") or "").strip(), path))

    for label, value, path in ordered:
        if path is not None and count_assignments(path, key) > 1:
            resolution.duplicate_sources.append(label)
        if not value:
            # Only an existing file with a blank assignment is worth reporting;
            # an absent file or an unset process variable is normal.
            if path is not None and path.is_file():
                resolution.empty_sources.append(label)
            continue
        resolution.candidates.append({"source": label, "fingerprint": fingerprint(value)})
        if not resolution.token:
            resolution.token = value
            resolution.source = label

    distinct = {c["fingerprint"] for c in resolution.candidates}
    if len(distinct) > 1:
        resolution.conflicting_sources = [c["source"] for c in resolution.candidates]

    return resolution


def resolve_token(env: Mapping | None = None, home: Path | None = None) -> str:
    """Convenience wrapper for callers that only need the value."""
    return resolve_buddy_web_token(env=env, home=home).token
