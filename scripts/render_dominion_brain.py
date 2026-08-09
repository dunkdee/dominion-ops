#!/usr/bin/env python3
"""Render the governed Dominion Brain into an Obsidian-compatible directory.

This renderer is intentionally local/offline. It reads only version-controlled
non-secret governance/registry files and writes a deterministic knowledge mirror.
It never activates Obsidian, contacts production, or reads environment secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "agents" / "registry.json"
AUTHORITY = REPO / "governance" / "authority_matrix.json"
OPERATING_MAP = REPO / "governance" / "DOMINION_OPERATING_MAP.md"
AGENT_STATE = REPO / "governance" / "AGENT_OPERATIONS_STATE.md"
RUNTIME_ALIGNMENT = REPO / "governance" / "RUNTIME_ALIGNMENT.md"
BRAIN_README = REPO / "brain" / "README.md"
TEAM_STATE = REPO / "brain" / "agent-team-current-state.md"

ROOT_DIRS = (
    "00-Constitution",
    "01-Founder-Authority",
    "02-Five-Council",
    "03-Control-Plane",
    "04-Agents",
    "05-Verticals",
    "06-Operations",
    "07-Incidents",
    "08-Evidence",
    "09-Revenue",
    "10-Architecture",
    "11-SOPs",
    "12-Decisions",
    "13-Learning",
    "14-Daily-State",
    "99-Archive",
)

AGENT_FILES = (
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


def _require_source(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"required governed source missing: {path.relative_to(REPO)}")
    return path.read_text(encoding="utf-8")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def _copy_governed(target: Path, relative: str, source: Path) -> None:
    text = _require_source(source)
    header = (
        "<!-- GENERATED FROM GOVERNED GITHUB SOURCE. EDIT SOURCE, NOT THIS MIRROR. -->\n"
        f"<!-- source: {source.relative_to(REPO).as_posix()} -->\n\n"
    )
    _atomic_write(target / relative, header + text)


def _agent_doc(agent: dict, filename: str) -> str:
    aid = agent["id"]
    role = agent["role"]
    purpose = agent["purpose"]
    state = agent["state"]
    permissions = agent.get("permissions", [])
    prohibited = agent.get("prohibited_actions", [])
    escalates = agent.get("escalates_to") or "none"

    common = (
        f"# {aid} — {filename[:-3]}\n\n"
        "> Generated from `agents/registry.json`. This note grants no authority beyond the registry.\n\n"
    )
    if filename == "00-Identity.md":
        body = f"- Agent ID: `{aid}`\n- Role: `{role}`\n- Lifecycle state: `{state}`\n"
    elif filename == "01-Mission.md":
        body = f"## Purpose\n\n{purpose}\n"
    elif filename == "02-Authority.md":
        body = "## Allowed\n\n" + "\n".join(f"- `{x}`" for x in permissions or ["none"]) + "\n\n"
        body += "## Prohibited\n\n" + "\n".join(f"- `{x}`" for x in prohibited or ["none"]) + "\n\n"
        body += f"## Escalation\n\n`{escalates}`\n"
    elif filename == "03-Inputs.md":
        body = "Inputs must be authorized, source-grounded, and appropriate to this agent's registry permissions.\n"
    elif filename == "04-Outputs.md":
        body = (
            "Every consequential report uses: `agent`, `duty`, `evidence`, `result`, `risks`, "
            "`next_action`, `human_approval_required`.\n"
        )
    elif filename == "05-Dependencies.md":
        body = (
            "- `governance/SYSTEM_CONSTITUTION.md`\n"
            "- `governance/DOMINION_OPERATING_MAP.md`\n"
            "- `governance/authority_matrix.json`\n"
            "- `agents/registry.json`\n"
            "- verified runtime evidence when live state matters\n"
        )
    elif filename == "06-SOPs.md":
        body = "Follow applicable version-controlled runbooks. Inventory → verify → reuse/connect → test → activate only within authority.\n"
    elif filename == "07-Health-and-Metrics.md":
        body = "No health claim is current without timestamped retrievable evidence. Record status, evidence source, timestamp, and next check.\n"
    elif filename == "08-Incidents-and-Lessons.md":
        body = "Record failures and corrective lessons without secrets or customer PII. Durable policy changes return to GitHub review.\n"
    elif filename == "09-Current-State.md":
        body = f"Registry lifecycle state: `{state}`. Runtime state must be separately verified before operational claims.\n"
    else:
        body = "Generated baseline. Durable changes are made in GitHub and mirrored after review.\n"
    return common + body


def _iter_output_files(target: Path) -> Iterable[Path]:
    for path in sorted(target.rglob("*")):
        if path.is_file():
            yield path


def render(target: Path) -> dict:
    if target.is_symlink():
        raise SystemExit("brain target must not be a symlink")
    if target.exists():
        if not target.is_dir():
            raise SystemExit("brain target must be a directory")
        if any(target.iterdir()):
            raise SystemExit("brain target must be empty")
    else:
        target.mkdir(parents=True, exist_ok=False)

    registry = json.loads(_require_source(REGISTRY))
    if not isinstance(registry.get("agents"), list) or not registry["agents"]:
        raise SystemExit("agent registry is empty or malformed")

    for directory in ROOT_DIRS:
        (target / directory).mkdir(parents=True, exist_ok=True)

    _copy_governed(target, "03-Control-Plane/DOMINION_OPERATING_MAP.md", OPERATING_MAP)
    _copy_governed(target, "03-Control-Plane/AGENT_OPERATIONS_STATE.md", AGENT_STATE)
    _copy_governed(target, "03-Control-Plane/RUNTIME_ALIGNMENT.md", RUNTIME_ALIGNMENT)
    _copy_governed(target, "03-Control-Plane/BRAIN_README.md", BRAIN_README)
    _copy_governed(target, "04-Agents/TEAM_CURRENT_STATE.md", TEAM_STATE)
    _copy_governed(target, "01-Founder-Authority/authority_matrix.json.md", AUTHORITY)

    registry_note = "# Agent Registry\n\n```json\n" + json.dumps(registry, indent=2) + "\n```\n"
    _atomic_write(target / "04-Agents/REGISTRY.md", registry_note)

    for agent in registry["agents"]:
        for filename in AGENT_FILES:
            _atomic_write(target / "04-Agents" / agent["id"] / filename, _agent_doc(agent, filename))

    manifest = []
    for path in _iter_output_files(target):
        if path.name == "MANIFEST.json":
            continue
        raw = path.read_bytes()
        manifest.append(
            {
                "path": path.relative_to(target).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        )
    manifest_doc = {
        "schema": "dominion-brain-manifest-v1",
        "source": "dunkdee/dominion-ops",
        "agent_count": len(registry["agents"]),
        "files": manifest,
    }
    _atomic_write(target / "MANIFEST.json", json.dumps(manifest_doc, indent=2))
    return manifest_doc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="Target Dominion-Brain directory")
    args = parser.parse_args()
    manifest = render(args.target.expanduser().resolve())
    print(f"BRAIN_RENDER=PASS agents={manifest['agent_count']} files={len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
