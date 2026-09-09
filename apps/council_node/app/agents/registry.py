"""Agent registry.

Every agent declares what it may and may not do. No agent receives
unrestricted shell, GitHub, finance, email, publishing, or credential access;
the registry refuses to register one that tries.

`authority` separates advice from action. An advisory agent's output is a
proposal even when it names a mutating capability -- the executor will not run
it. Only an agent explicitly registered as `executing` can act, and even then
the policy evaluator still has to allow the specific capability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

GOVERNANCE_NAME = "RADAH_MEMSHALAH"

# Capabilities no agent may ever hold, regardless of its registration.
UNIVERSALLY_FORBIDDEN = frozenset({
    "shell.unrestricted",
    "secret_readback",
    "financial_transfer",
    "credential.export",
    "governance.modify",
})


class AgentError(RuntimeError):
    """An agent registration was rejected."""


class AgentClass(str, Enum):
    OBSERVER = "observer"
    RESEARCHER = "researcher"
    PLANNER = "planner"
    WORKER = "worker"
    REVIEWER = "reviewer"
    PUBLISHER = "publisher"
    COUNCIL = "council"
    RECOVERY = "recovery"


class Authority(str, Enum):
    ADVISORY = "advisory"    # output is a proposal, never an action
    EXECUTING = "executing"  # may act, subject to the policy evaluator


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    name: str
    agent_class: AgentClass
    authority: Authority = Authority.ADVISORY
    allowed_capabilities: tuple[str, ...] = field(default_factory=tuple)
    forbidden_capabilities: tuple[str, ...] = field(default_factory=tuple)
    lanes: tuple[str, ...] = field(default_factory=tuple)
    governance: str = GOVERNANCE_NAME
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id, "name": self.name,
            "class": self.agent_class.value, "authority": self.authority.value,
            "allowed_capabilities": list(self.allowed_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "lanes": list(self.lanes), "governance": self.governance,
            "enabled": self.enabled,
        }

    @property
    def may_execute(self) -> bool:
        return self.enabled and self.authority is Authority.EXECUTING


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}

    def register(self, record: AgentRecord) -> AgentRecord:
        if record.governance != GOVERNANCE_NAME:
            raise AgentError(
                f"agent '{record.agent_id}' does not declare {GOVERNANCE_NAME} governance"
            )
        overreach = set(record.allowed_capabilities) & UNIVERSALLY_FORBIDDEN
        if overreach:
            raise AgentError(
                f"agent '{record.agent_id}' requests universally forbidden "
                f"capabilities: {sorted(overreach)}"
            )
        if record.agent_id in self._agents:
            raise AgentError(f"agent '{record.agent_id}' is already registered")
        self._agents[record.agent_id] = record
        return record

    def get(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def require(self, agent_id: str) -> AgentRecord:
        record = self.get(agent_id)
        if record is None:
            raise AgentError(f"agent '{agent_id}' is not registered")
        if not record.enabled:
            raise AgentError(f"agent '{agent_id}' is registered but disabled")
        return record

    def all(self) -> list[AgentRecord]:
        return [self._agents[k] for k in sorted(self._agents)]

    def effective_forbidden(self, record: AgentRecord) -> tuple[str, ...]:
        """The agent's own denials plus the universal ones."""
        return tuple(sorted(set(record.forbidden_capabilities) | UNIVERSALLY_FORBIDDEN))

    @classmethod
    def from_file(cls, path: Path | str) -> "AgentRegistry":
        p = Path(path).expanduser()
        if not p.is_file():
            raise AgentError(f"agent registry file is missing: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        registry = cls()
        for row in data.get("agents", []):
            registry.register(AgentRecord(
                agent_id=str(row["agent_id"]),
                name=str(row.get("name", row["agent_id"])),
                agent_class=AgentClass(row.get("class", "worker")),
                authority=Authority(row.get("authority", "advisory")),
                allowed_capabilities=tuple(row.get("allowed_capabilities", [])),
                forbidden_capabilities=tuple(row.get("forbidden_capabilities", [])),
                lanes=tuple(row.get("lanes", [])),
                governance=str(row.get("governance", GOVERNANCE_NAME)),
                enabled=bool(row.get("enabled", True)),
            ))
        return registry
