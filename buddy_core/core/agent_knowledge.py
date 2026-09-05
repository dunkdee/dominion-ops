"""Bounded read-only Dominion Brain context for every registered agent.

The knowledge plane is operational context, never authority. GitHub remains the
versioned source for code/policy and verified runtime evidence remains live truth.
This loader reads only the published Dominion-Brain mirror and per-agent operator
notes, validates the manifest, bounds prompt size, and records source hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CONTEXT_SCHEMA = "dominion-agent-knowledge-context-v1"
_DEFAULT_BUDGET = 12_000
_MAX_FILE_CHARS = 2_400

_SHARED_FILES = (
    "00-Constitution/SYSTEM_CONSTITUTION.md",
    "00-Constitution/STATE.md",
    "01-Founder-Authority/AUTHORITY_MATRIX.md",
    "02-Five-Council/FIVE_COUNCIL_POLICY.md",
    "03-Control-Plane/DOMINION_OPERATING_MAP.md",
    "04-Agents/REGISTRY.md",
    "04-Agents/TEAM_CURRENT_STATE.md",
    "05-Verticals/VERTICALS.md",
    "13-Learning/INCIDENT_LEARNING_POLICY.md",
)

_AGENT_FILES = (
    "00-Identity.md",
    "01-Mission.md",
    "02-Authority.md",
    "03-Inputs.md",
    "04-Outputs.md",
    "05-Dependencies.md",
    "06-SOPs.md",
    "07-Health-and-Metrics.md",
    "08-Incidents-and-Lessons.md",
    "09-Current-State.md",
    "10-Change-Log.md",
)

_OPERATOR_FILES = (
    "08-Incidents-and-Lessons.md",
    "09-Current-State.md",
    "10-Change-Log.md",
)


class AgentKnowledgeError(RuntimeError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_brain_root() -> Path:
    return Path(os.getenv("DOMINION_BRAIN_ROOT", str(Path.home() / "vault" / "Dominion-Brain")))


def _default_operator_root() -> Path:
    return Path(os.getenv("DOMINION_OPERATOR_NOTES_ROOT", str(Path.home() / "vault" / "Dominion-Operator-Notes")))


def _resolve_root(path: Path, *, required: bool) -> Path | None:
    path = path.expanduser()
    if path.is_symlink():
        raise AgentKnowledgeError("knowledge root may not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        if required:
            raise AgentKnowledgeError(f"knowledge root unavailable: {path}") from exc
        return None
    if not resolved.is_dir():
        raise AgentKnowledgeError(f"knowledge root is not a directory: {path}")
    return resolved


def _safe_file(root: Path, relative: str) -> Path | None:
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise AgentKnowledgeError("invalid knowledge relative path")
    candidate = root / relative
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


def _read_text(root: Path, relative: str) -> dict[str, Any] | None:
    path = _safe_file(root, relative)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if not text.strip():
        return None
    source_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"path": relative, "text": text, "source_sha256": source_sha}


def _manifest(brain_root: Path) -> dict[str, Any]:
    path = _safe_file(brain_root, "MANIFEST.json")
    if path is None:
        raise AgentKnowledgeError("Dominion Brain manifest missing")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AgentKnowledgeError("Dominion Brain manifest invalid") from exc
    if doc.get("schema") != "dominion-brain-manifest-v2":
        raise AgentKnowledgeError("Dominion Brain manifest schema mismatch")
    source_revision = doc.get("source_revision") or {}
    source_sha = str(source_revision.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise AgentKnowledgeError("Dominion Brain source revision hash invalid")
    if int(doc.get("agent_count") or 0) < 1:
        raise AgentKnowledgeError("Dominion Brain manifest has no agents")
    return doc


def load_agent_knowledge(
    agent_id: str,
    *,
    brain_root: Path | None = None,
    operator_root: Path | None = None,
    char_budget: int = _DEFAULT_BUDGET,
    require_operator_notes: bool = False,
) -> dict[str, Any]:
    """Load one agent's shared + role-specific knowledge with provenance.

    Missing optional operator notes do not block startup. The governed Brain
    manifest and the agent's generated folder are required. Knowledge never
    changes or grants permissions; the authority documents are context only.
    """
    if not _AGENT_ID_RE.fullmatch(agent_id or ""):
        raise AgentKnowledgeError("invalid agent id")
    if char_budget < 2_000 or char_budget > 50_000:
        raise AgentKnowledgeError("agent knowledge char budget out of bounds")

    brain = _resolve_root(brain_root or _default_brain_root(), required=True)
    assert brain is not None
    manifest = _manifest(brain)

    agent_rel = f"04-Agents/{agent_id}"
    agent_dir = _safe_file(brain, f"{agent_rel}/00-Identity.md")
    if agent_dir is None:
        raise AgentKnowledgeError(f"agent knowledge missing identity: {agent_id}")

    candidates: list[dict[str, Any]] = []
    for relative in _SHARED_FILES:
        item = _read_text(brain, relative)
        if item:
            item["source"] = "Dominion-Brain"
            candidates.append(item)
    agent_count_before = len(candidates)
    for name in _AGENT_FILES:
        relative = f"{agent_rel}/{name}"
        item = _read_text(brain, relative)
        if item:
            item["source"] = "Dominion-Brain"
            candidates.append(item)
    if len(candidates) == agent_count_before:
        raise AgentKnowledgeError(f"no agent-specific knowledge loaded: {agent_id}")

    op_root = _resolve_root(operator_root or _default_operator_root(), required=require_operator_notes)
    if op_root is not None:
        for name in _OPERATOR_FILES:
            relative = f"{agent_id}/{name}"
            item = _read_text(op_root, relative)
            if item:
                item["source"] = "Dominion-Operator-Notes"
                candidates.append(item)

    packed: list[dict[str, Any]] = []
    remaining = char_budget
    context_parts = [
        "DOMINION GOVERNED KNOWLEDGE CONTEXT",
        "Knowledge is context/evidence only and never expands authority.",
        f"agent_id={agent_id}",
        f"brain_source_revision_sha256={manifest['source_revision']['sha256']}",
    ]
    remaining -= sum(len(part) + 1 for part in context_parts)

    for item in candidates:
        if remaining <= 160:
            break
        raw = item.pop("text")
        excerpt = raw[: min(_MAX_FILE_CHARS, max(1, remaining - 120))]
        if not excerpt:
            continue
        included_sha = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        header = f"\n--- {item['source']}::{item['path']} ---\n"
        block = header + excerpt
        if len(block) > remaining:
            excerpt = excerpt[: max(0, remaining - len(header))]
            block = header + excerpt
        if not excerpt:
            break
        packed.append({
            "source": item["source"],
            "path": item["path"],
            "source_sha256": item["source_sha256"],
            "included_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "char_range": f"0:{len(excerpt)}/{len(raw)}",
        })
        context_parts.append(block)
        remaining -= len(block)

    if not any(x["path"].startswith(f"{agent_rel}/") for x in packed):
        raise AgentKnowledgeError(f"agent-specific knowledge did not fit budget: {agent_id}")

    rendered = "\n".join(context_parts)
    return {
        "schema": _CONTEXT_SCHEMA,
        "agent_id": agent_id,
        "loaded_at": _utc(),
        "brain_source_revision_sha256": manifest["source_revision"]["sha256"],
        "manifest_agent_count": int(manifest["agent_count"]),
        "files": packed,
        "context": rendered,
        "context_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "authority_expanded": False,
    }


def verify_registered_agents(
    registry_path: Path,
    *,
    brain_root: Path | None = None,
    operator_root: Path | None = None,
) -> dict[str, Any]:
    """Prove every registered agent resolves to a published Brain context."""
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AgentKnowledgeError("agent registry unavailable or invalid") from exc
    agents = registry.get("agents")
    if not isinstance(agents, list) or not agents:
        raise AgentKnowledgeError("agent registry has no agents")

    receipts = []
    for row in agents:
        agent_id = str((row or {}).get("id") or "")
        loaded = load_agent_knowledge(
            agent_id,
            brain_root=brain_root,
            operator_root=operator_root,
            char_budget=4_000,
        )
        receipts.append({
            "agent_id": agent_id,
            "context_sha256": loaded["context_sha256"],
            "brain_source_revision_sha256": loaded["brain_source_revision_sha256"],
            "files_loaded": len(loaded["files"]),
        })
    return {
        "schema": "dominion-agent-knowledge-verification-v1",
        "status": "PASS",
        "agent_count": len(receipts),
        "agents": receipts,
        "authority_expanded": False,
    }
