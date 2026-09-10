"""Capability registry — what an agent is permitted to do.

Rule 6: no external action without an explicit allowed capability. This
registry is the allowlist, and lookups are fail-closed in both directions:
an unregistered capability is denied, and a capability the agent has not been
granted is denied even if it exists.

Forbidden capabilities are checked before allowed ones, so an explicit denial
always wins over an explicit grant. That ordering matters when an agent's
allow-list is broad and a specific action must stay off-limits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class CapabilityError(RuntimeError):
    """The capability registry could not be loaded."""


@dataclass(frozen=True)
class Capability:
    id: str
    classification: str      # read | write | external | destructive
    auth_required: bool
    enabled: bool
    description: str = ""

    @property
    def is_mutating(self) -> bool:
        return self.classification in {"write", "external", "destructive"}


class CapabilityRegistry:
    def __init__(self, capabilities: dict[str, Capability]) -> None:
        self._caps = dict(capabilities)

    @classmethod
    def from_file(cls, path: Path | str) -> "CapabilityRegistry":
        p = Path(path).expanduser()
        if not p.is_file():
            raise CapabilityError(f"capability registry is missing: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityError(f"capability registry is unreadable: {exc}") from exc

        rows = data.get("capabilities")
        if not isinstance(rows, list) or not rows:
            raise CapabilityError("capability registry declares no capabilities")

        caps: dict[str, Capability] = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            cap_id = str(row["id"])
            caps[cap_id] = Capability(
                id=cap_id,
                classification=str(row.get("classification", "write")),
                auth_required=bool(row.get("auth_required", True)),
                enabled=bool(row.get("enabled", False)),
                description=str(row.get("description", "")),
            )
        if not caps:
            raise CapabilityError("capability registry contained no usable entries")
        return cls(caps)

    def get(self, capability_id: str) -> Capability | None:
        return self._caps.get(capability_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._caps))

    def permits(
        self,
        capability_id: str,
        *,
        allowed: tuple[str, ...],
        forbidden: tuple[str, ...],
    ) -> tuple[bool, str]:
        """Return (permitted, reason). Reason is always populated on denial."""
        # Explicit denial outranks any grant.
        if capability_id in forbidden:
            return False, f"capability '{capability_id}' is explicitly forbidden for this agent"

        cap = self.get(capability_id)
        if cap is None:
            return False, f"capability '{capability_id}' is not in the registry"
        if not cap.enabled:
            return False, f"capability '{capability_id}' is registered but disabled"
        if capability_id not in allowed:
            return False, f"capability '{capability_id}' is not granted to this agent"
        return True, "granted"
