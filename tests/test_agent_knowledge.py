from __future__ import annotations

import json
from pathlib import Path

import pytest

from buddy_core.core.agent_knowledge import (
    AgentKnowledgeError,
    load_agent_knowledge,
    verify_registered_agents,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "agents" / "registry.json"


def _build_brain(tmp_path: Path, agent_ids: list[str]) -> tuple[Path, Path]:
    brain = tmp_path / "vault" / "Dominion-Brain"
    operator = tmp_path / "vault" / "Dominion-Operator-Notes"
    brain.mkdir(parents=True)
    operator.mkdir(parents=True)
    (brain / "MANIFEST.json").write_text(
        json.dumps(
            {
                "schema": "dominion-brain-manifest-v2",
                "agent_count": len(agent_ids),
                "source_revision": {"sha256": "a" * 64},
            }
        ),
        encoding="utf-8",
    )
    shared = brain / "00-Constitution"
    shared.mkdir(parents=True)
    (shared / "SYSTEM_CONSTITUTION.md").write_text(
        "# Constitution\nEvidence first. Knowledge never expands authority.\n",
        encoding="utf-8",
    )
    for agent_id in agent_ids:
        folder = brain / "04-Agents" / agent_id
        folder.mkdir(parents=True)
        (folder / "00-Identity.md").write_text(
            f"# {agent_id}\nThis is governed context for {agent_id}.\n",
            encoding="utf-8",
        )
    return brain, operator


def test_every_registered_agent_resolves_to_governed_context(tmp_path):
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = [row["id"] for row in registry["agents"]]
    brain, operator = _build_brain(tmp_path, ids)

    receipt = verify_registered_agents(
        REGISTRY,
        brain_root=brain,
        operator_root=operator,
    )

    assert receipt["status"] == "PASS"
    assert receipt["agent_count"] == len(ids)
    assert {row["agent_id"] for row in receipt["agents"]} == set(ids)
    assert receipt["authority_expanded"] is False
    assert all(len(row["context_sha256"]) == 64 for row in receipt["agents"])


def test_agent_context_contains_shared_and_agent_specific_knowledge(tmp_path):
    brain, operator = _build_brain(tmp_path, ["buddy"])
    notes = operator / "buddy"
    notes.mkdir(parents=True)
    (notes / "09-Current-State.md").write_text("# Current State\nRevenue lane active.\n", encoding="utf-8")

    result = load_agent_knowledge(
        "buddy",
        brain_root=brain,
        operator_root=operator,
    )

    assert result["schema"] == "dominion-agent-knowledge-context-v1"
    assert result["agent_id"] == "buddy"
    assert result["brain_source_revision_sha256"] == "a" * 64
    assert result["authority_expanded"] is False
    paths = {row["path"] for row in result["files"]}
    assert "00-Constitution/SYSTEM_CONSTITUTION.md" in paths
    assert "04-Agents/buddy/00-Identity.md" in paths
    assert "buddy/09-Current-State.md" in paths
    assert "Knowledge is context/evidence only and never expands authority." in result["context"]


def test_missing_agent_specific_brain_context_fails_closed(tmp_path):
    brain, operator = _build_brain(tmp_path, ["buddy"])
    (brain / "04-Agents" / "buddy" / "00-Identity.md").unlink()

    with pytest.raises(AgentKnowledgeError, match="missing identity"):
        load_agent_knowledge("buddy", brain_root=brain, operator_root=operator)


def test_context_budget_is_bounded(tmp_path):
    brain, operator = _build_brain(tmp_path, ["buddy"])
    folder = brain / "04-Agents" / "buddy"
    (folder / "01-Mission.md").write_text("X" * 20_000, encoding="utf-8")

    result = load_agent_knowledge(
        "buddy",
        brain_root=brain,
        operator_root=operator,
        char_budget=4_000,
    )

    assert len(result["context"]) <= 4_000
    assert result["authority_expanded"] is False


def test_invalid_manifest_hash_is_rejected(tmp_path):
    brain, operator = _build_brain(tmp_path, ["buddy"])
    manifest = json.loads((brain / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["source_revision"]["sha256"] = "not-a-hash"
    (brain / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AgentKnowledgeError, match="source revision hash invalid"):
        load_agent_knowledge("buddy", brain_root=brain, operator_root=operator)
