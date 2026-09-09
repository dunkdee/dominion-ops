"""The constitutional layer — Layer A memory, never agent-writable.

This loads Dominion's *existing* governance files rather than defining a
second set. `governance/authority_matrix.json` and
`governance/five_council_policy.json` already encode risk levels, veto
domains and council composition for the whole estate; a Council Node that
invented its own copy would create the second source of truth that rule 15
forbids.

Loading is fail-closed. A missing or malformed governance file raises rather
than falling back to a permissive default, because a governance layer that
degrades into "allow" under error is worse than no governance layer at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

GOVERNING_NAME = "RADAH MEMSHALAH"


class ConstitutionError(RuntimeError):
    """Governance could not be loaded or is internally inconsistent."""


class Status(str, Enum):
    """The only status values the system may use (work order §2)."""

    DONE = "DONE"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    HOLD = "HOLD"

    @classmethod
    def blocking(cls) -> frozenset["Status"]:
        """Statuses that must stop a release. UNKNOWN blocks by design."""
        return frozenset({cls.BLOCKED, cls.UNKNOWN, cls.HOLD})


@dataclass(frozen=True)
class RiskLevel:
    name: str
    council_approvals_required: int
    human_approval_required: bool
    reject: bool = False


class Constitution:
    """Read-only view over Dominion's governance files."""

    AUTHORITY_FILE = "authority_matrix.json"
    COUNCIL_FILE = "five_council_policy.json"

    def __init__(self, governance_dir: Path | str) -> None:
        self.dir = Path(governance_dir).expanduser()
        self._authority = self._load(self.AUTHORITY_FILE)
        self._council = self._load(self.COUNCIL_FILE)
        self._validate()

    def _load(self, name: str) -> dict:
        path = self.dir / name
        if not path.is_file():
            raise ConstitutionError(f"governance file is missing: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConstitutionError(f"governance file {name} is unreadable: {exc}") from exc
        if not isinstance(data, dict):
            raise ConstitutionError(f"governance file {name} is not an object")
        return data

    def _validate(self) -> None:
        if self._authority.get("default_behavior") != "deny":
            raise ConstitutionError(
                "authority_matrix default_behavior must be 'deny'; refusing to run fail-open"
            )
        if not self._authority.get("risk_levels"):
            raise ConstitutionError("authority_matrix defines no risk levels")
        if not self._council.get("councils"):
            raise ConstitutionError("five_council_policy defines no councils")

    # ── revision ────────────────────────────────────────────────────────

    @property
    def revision(self) -> str:
        """Hash of the governance in force, stamped into every receipt."""
        canonical = json.dumps(
            {"authority": self._authority, "council": self._council},
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ── risk ────────────────────────────────────────────────────────────

    def risk_level(self, name: str) -> RiskLevel:
        levels = self._authority.get("risk_levels", {})
        raw = levels.get(name)
        if not isinstance(raw, dict):
            raise ConstitutionError(f"unknown risk level: {name}")
        return RiskLevel(
            name=name,
            council_approvals_required=int(raw.get("council_approvals_required", 0)),
            human_approval_required=bool(raw.get("human_approval_required", False)),
            reject=raw.get("action") == "reject",
        )

    def risk_for_action(self, action_id: str) -> str | None:
        """The declared risk level for an action, or None if undeclared.

        Undeclared is not "low". The evaluator treats None as UNKNOWN, which
        blocks -- an action nobody classified has not been approved.
        """
        for entry in self._authority.get("actions", []):
            if isinstance(entry, dict) and entry.get("id") == action_id:
                level = entry.get("risk")
                return str(level) if level else None
        return None

    # ── councils ────────────────────────────────────────────────────────

    @property
    def council_ids(self) -> tuple[str, ...]:
        return tuple(
            str(c["id"]) for c in self._council.get("councils", []) if isinstance(c, dict) and c.get("id")
        )

    @property
    def veto_councils(self) -> frozenset[str]:
        """Councils whose single VETO is independently blocking."""
        declared = self._authority.get("independent_veto_domains", [])
        from_policy = {
            str(c["id"]) for c in self._council.get("councils", [])
            if isinstance(c, dict) and c.get("veto") and c.get("id")
        }
        return frozenset({str(d) for d in declared} | from_policy)

    @property
    def preserve_dissent(self) -> bool:
        return bool(self._council.get("preserve_dissent", True))

    @property
    def proposer_may_not_be_sole_approver(self) -> bool:
        return bool(self._council.get("proposer_may_not_be_sole_approver", True))
