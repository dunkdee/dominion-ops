"""Composition root.

One place builds the object graph, so tests can construct the same graph
against temporary directories without importing the FastAPI app. Nothing here
reads a secret out loud; `Settings.redacted()` is the only public view.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .agents.registry import AgentRegistry
from .config import Settings, settings as load_settings
from .governance.capabilities import CapabilityRegistry
from .governance.constitution import Constitution
from .governance.evaluator import PolicyEvaluator
from .governance.founder_gate import FounderGate
from .governance.release_gate import ReleaseGate
from .memory.store import MemoryStore
from .models.anthropic_adapter import AnthropicAdapter
from .models.base import ModelTier
from .models.ollama import OllamaAdapter
from .models.openai_adapter import OpenAIAdapter
from .models.router import ModelRouter
from .orchestration.executor import Executor
from .orchestration.scheduler import GovernanceSweep
from .receipts.writer import ReceiptWriter


def code_revision() -> str:
    """Current git SHA, or 'unknown'. Never guessed."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@dataclass
class Services:
    settings: Settings
    constitution: Constitution
    capabilities: CapabilityRegistry
    founder_gate: FounderGate
    evaluator: PolicyEvaluator
    release_gate: ReleaseGate
    agents: AgentRegistry
    receipts: ReceiptWriter
    executor: Executor
    memory: MemoryStore
    models: ModelRouter
    sweep: GovernanceSweep
    code_revision: str


def build_services(
    settings: Settings | None = None,
    *,
    state_dir: Path | None = None,
) -> Services:
    cfg = settings or load_settings()
    secrets = cfg.secret_values()
    state = Path(state_dir) if state_dir else cfg.receipt_dir.parent

    constitution = Constitution(cfg.governance_dir)
    capabilities = CapabilityRegistry.from_file(
        Path("buddy_core/config/capability_registry.json")
    )
    founder_gate = FounderGate(cfg.founder_token, state / "founder_holds.json")
    evaluator = PolicyEvaluator(constitution, capabilities, founder_gate)
    receipts = ReceiptWriter(cfg.receipt_dir)
    agents = AgentRegistry()
    revision = code_revision()

    adapters = [
        OllamaAdapter(cfg.ollama_url, cfg.local_model, tier=ModelTier.LOCAL_LIGHT),
        OpenAIAdapter(cfg.openai_api_key, enabled=cfg.external_models_enabled),
        AnthropicAdapter(cfg.anthropic_api_key, enabled=cfg.external_models_enabled),
    ]

    return Services(
        settings=cfg,
        constitution=constitution,
        capabilities=capabilities,
        founder_gate=founder_gate,
        evaluator=evaluator,
        release_gate=ReleaseGate(constitution),
        agents=agents,
        receipts=receipts,
        executor=Executor(
            evaluator, agents, receipts,
            code_revision=revision, secret_values=secrets,
        ),
        memory=MemoryStore(state / "memory.db"),
        models=ModelRouter(
            adapters, secret_values=secrets, allow_external=cfg.external_models_enabled,
        ),
        sweep=GovernanceSweep(
            receipts,
            stale_hours=cfg.lane_stale_hours,
            policy_revision=constitution.revision,
            code_revision=revision,
        ),
        code_revision=revision,
    )


@lru_cache(maxsize=1)
def services() -> Services:
    return build_services()
