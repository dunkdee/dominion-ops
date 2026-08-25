#!/usr/bin/env python3
"""Render a governed Dominion Brain generation for Obsidian.

The renderer is local/offline and stage-only: the target must not already exist.
It reads only version-controlled governance/registry sources, never environment
secrets, and cleans a failed partial generation. Production publication is a
separate governed synchronization step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[1]

SYSTEM_CONSTITUTION = REPO / "governance" / "SYSTEM_CONSTITUTION.md"
STATE = REPO / "STATE.md"
REPOSITORY_README = REPO / "README.md"
REGISTRY = REPO / "agents" / "registry.json"
AUTHORITY = REPO / "governance" / "authority_matrix.json"
FIVE_COUNCIL = REPO / "governance" / "five_council_policy.json"
INCIDENT_LEARNING = REPO / "governance" / "incident_learning_policy.json"
VERTICALS = REPO / "governance" / "verticals.json"
CONTROL_PLANE = REPO / "architecture" / "CONTROL_PLANE.md"
OPERATING_MAP = REPO / "governance" / "DOMINION_OPERATING_MAP.md"
AGENT_STATE = REPO / "governance" / "AGENT_OPERATIONS_STATE.md"
RUNTIME_ALIGNMENT = REPO / "governance" / "RUNTIME_ALIGNMENT.md"
BRAIN_README = REPO / "brain" / "README.md"
TEAM_STATE = REPO / "brain" / "agent-team-current-state.md"

GOVERNED_SOURCES = (
    SYSTEM_CONSTITUTION,
    STATE,
    REPOSITORY_README,
    REGISTRY,
    AUTHORITY,
    FIVE_COUNCIL,
    INCIDENT_LEARNING,
    VERTICALS,
    CONTROL_PLANE,
    OPERATING_MAP,
    AGENT_STATE,
    RUNTIME_ALIGNMENT,
    BRAIN_README,
    TEAM_STATE,
)

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

OPERATOR_BRIDGE_FILES = frozenset(
    {"08-Incidents-and-Lessons.md", "09-Current-State.md", "10-Change-Log.md"}
)
OPERATOR_NOTES_ROOT = "Dominion-Operator-Notes"


COMMAND_STATE_NOTES = (
    ("Today.md", "Current governed priorities and the next exact operational action."),
    ("Executive-Dashboard.md", "Executive summary of verified, blocked, and unknown operating state."),
    ("Current-Blockers.md", "Blockers that prevent governed execution or truthful completion claims."),
    ("Founder-Approvals.md", "Pending and completed Founder approval checkpoints without secret material."),
    ("Change-Queue.md", "Ordered governed changes awaiting evidence, review, or execution authority."),
    ("Evidence-Freshness.md", "Freshness register for evidence used in operational decisions."),
)

ARCHITECTURE_NOTES = (
    (
        "10-Architecture/Foundation-VM.md",
        "Foundation VM",
        "Production runtime authority. Current service state must come from timestamped VM evidence.",
    ),
    (
        "10-Architecture/GCP-Storage.md",
        "GCP Storage",
        "Storage inventory, retention, and restore claims require current Google Cloud evidence.",
    ),
    (
        "10-Architecture/GitHub-Control-Source.md",
        "GitHub Control Source",
        "GitHub is authoritative for versioned law, policy, code, contracts, and deployment records.",
    ),
    (
        "10-Architecture/Obsidian-Boundary.md",
        "Obsidian Boundary",
        "Obsidian is the operational context mirror; it does not replace GitHub or live runtime evidence.",
    ),
)

EVIDENCE_NOTES = (
    (
        "08-Evidence/PR-90-Ecosystem-Reconciliation.md",
        "PR 90 — Ecosystem Reconciliation",
        "https://github.com/dunkdee/dominion-ops/pull/90",
    ),
    (
        "08-Evidence/PR-91-One-Percent-Blueprint.md",
        "PR 91 — One-Percent Blueprint",
        "https://github.com/dunkdee/dominion-ops/pull/91",
    ),
    (
        "08-Evidence/Issue-92-Execution-Packet-001.md",
        "Issue 92 — Execution Packet 001",
        "https://github.com/dunkdee/dominion-ops/issues/92",
    ),
    (
        "08-Evidence/Issue-93-Archive-Repair.md",
        "Issue 93 — Archive Repair",
        "https://github.com/dunkdee/dominion-ops/issues/93",
    ),
)

OPERATIONS_NOTES = (
    (
        "06-Operations/Storage-Capacity.md",
        "Storage Capacity",
        "Capacity values are live-runtime facts and remain UNKNOWN until a timestamped inventory is attached.",
    ),
    (
        "06-Operations/Backup-Restore-Register.md",
        "Backup and Restore Register",
        "Backup existence is not a restore claim; each entry requires retrievable verification evidence.",
    ),
)

SERVICE_NOTES = (
    ("Foundation-VM-Host.md", "Foundation VM host", "Production compute host and runtime boundary."),
    ("Caddy-Edge.md", "Caddy edge", "Authenticated public edge and reverse-proxy boundary."),
    ("Dominion-Web.md", "Dominion Web", "Primary Dominion web application service."),
    ("Wix-Agent.md", "Wix Agent", "Wix integration and storefront-control service."),
    ("Baby-API.md", "Baby API", "Baby API application service."),
    ("Browser-Agents.md", "Browser Agents", "Governed browser-automation services."),
    ("Obsidian-Remote.md", "Obsidian Remote", "Phone-first and laptop-accessible operational memory interface."),
    ("Movie-Video-Studio.md", "Movie / Video Studio", "Governed movie and video production service."),
    ("n8n.md", "n8n", "Workflow-orchestration service."),
    ("PostgreSQL.md", "PostgreSQL", "Relational persistence service."),
    ("Dominion-Alpha-Paper-Trading.md", "Dominion Alpha / paper trading", "Paper-only trading research and evidence service."),
)
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _require_source(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"required governed source missing: {path.relative_to(REPO)}")
    return path.read_text(encoding="utf-8")


def _validate_agent_id(value: object) -> str:
    aid = str(value or "")
    if aid in {".", ".."} or not _AGENT_ID_RE.fullmatch(aid):
        raise SystemExit(f"unsafe agent id in governed registry: {aid!r}")
    return aid


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise SystemExit(f"refusing symlinked output parent: {path.parent}")
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


def _markdown_source(path: Path, text: str) -> str:
    rel = path.relative_to(REPO).as_posix()
    header = (
        "<!-- GENERATED FROM GOVERNED GITHUB SOURCE. EDIT SOURCE, NOT THIS MIRROR. -->\n"
        f"<!-- source: {rel} -->\n\n"
    )
    if path.suffix == ".json":
        title = path.stem.replace("_", " ").title()
        return header + f"# {title}\n\n```json\n{text.rstrip()}\n```\n"
    return header + text


def _copy_governed(target: Path, relative: str, source: Path) -> None:
    _atomic_write(target / relative, _markdown_source(source, _require_source(source)))


def _source_digest(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(REPO).as_posix()):
        rel = path.relative_to(REPO).as_posix().encode("utf-8")
        raw = path.read_bytes()
        digest.update(rel)
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _authority_doc(agent: dict, authority: dict) -> str:
    role = str(agent.get("role", ""))
    actions = authority.get("actions") if isinstance(authority.get("actions"), list) else []
    risk_levels = authority.get("risk_levels") if isinstance(authority.get("risk_levels"), dict) else {}
    effective = []
    for action in actions:
        if not isinstance(action, dict) or role not in action.get("allowed_roles", []):
            continue
        risk = str(action.get("risk", "unknown"))
        risk_rule = risk_levels.get(risk) if isinstance(risk_levels.get(risk), dict) else {}
        effective.append(
            {
                "id": str(action.get("id", "unknown")),
                "risk": risk,
                "council": risk_rule.get("council_approvals_required", "unknown"),
                "human": risk_rule.get("human_approval_required", "unknown"),
                "constraints": [str(x) for x in action.get("constraints", [])],
            }
        )

    lines = [
        "## Effective governed action permissions",
        "",
        f"Default behavior: `{authority.get('default_behavior', 'deny')}`.",
        "The authority matrix, risk rule, constraints, approvals, and current lifecycle gate all apply together.",
        "",
    ]
    if effective:
        for item in effective:
            constraints = ", ".join(f"`{x}`" for x in item["constraints"]) or "none listed"
            lines.extend(
                [
                    f"### `{item['id']}`",
                    f"- Risk: `{item['risk']}`",
                    f"- Council approvals required by risk rule: `{item['council']}`",
                    f"- Human approval required by risk rule: `{item['human']}`",
                    f"- Constraints: {constraints}",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "No action ID in the current authority matrix is delegated directly to this role.",
                "Consequential actions therefore remain default-deny unless a canonical policy explicitly authorizes them.",
                "",
            ]
        )

    caps = [str(x) for x in agent.get("permissions", [])]
    prohibited = [str(x) for x in agent.get("prohibited_actions", [])]
    lines.extend(
        [
            "## Registry capabilities — descriptive, not independent authority",
            "",
            *(f"- `{x}`" for x in (caps or ["none"])),
            "",
            "## Registry prohibitions",
            "",
            *(f"- `{x}`" for x in (prohibited or ["none"])),
            "",
            "## Escalation",
            "",
            f"`{agent.get('escalates_to') or 'none'}`",
            "",
        ]
    )
    return "\n".join(lines)


def _agent_doc(agent: dict, filename: str, authority: dict) -> str:
    aid = _validate_agent_id(agent.get("id"))
    role = str(agent.get("role", "unknown"))
    purpose = str(agent.get("purpose", ""))
    state = str(agent.get("state", "UNKNOWN"))

    common = (
        f"# {aid} — {filename[:-3]}\n\n"
        "> Generated from governed GitHub sources. This mirror grants no authority beyond effective policy.\n\n"
    )
    if filename == "00-Identity.md":
        body = f"- Agent ID: `{aid}`\n- Role: `{role}`\n- Registry lifecycle state: `{state}`\n"
    elif filename == "01-Mission.md":
        body = f"## Purpose\n\n{purpose}\n"
    elif filename == "02-Authority.md":
        body = _authority_doc(agent, authority)
    elif filename == "03-Inputs.md":
        body = "Inputs must be authorized, source-grounded, correctly classified, and allowed by effective policy.\n"
    elif filename == "04-Outputs.md":
        body = (
            "Every consequential report uses: `agent`, `duty`, `evidence`, `result`, `risks`, "
            "`next_action`, `human_approval_required`. Truth states are `VERIFIED`, `INFERRED`, `UNKNOWN`, or `BLOCKED`.\n"
        )
    elif filename == "05-Dependencies.md":
        body = (
            "## Governing dependencies\n\n"
            "1. [[00-Constitution/SYSTEM_CONSTITUTION]]\n"
            "2. [[00-Constitution/STATE]]\n"
            "3. [[00-Constitution/REPOSITORY_README]]\n"
            "4. [[04-Agents/REGISTRY]]\n"
            "5. [[01-Founder-Authority/AUTHORITY_MATRIX]]\n"
            "6. [[02-Five-Council/FIVE_COUNCIL_POLICY]]\n"
            "7. [[13-Learning/INCIDENT_LEARNING_POLICY]]\n"
            "8. [[05-Verticals/VERTICALS]]\n"
            "9. [[03-Control-Plane/CONTROL_PLANE]]\n"
            "10. Applicable runbook/incident record\n"
            "11. Verified live runtime evidence before production claims\n"
        )
    elif filename == "06-SOPs.md":
        body = (
            "Follow the canonical required reading order in [[03-Control-Plane/DOMINION_OPERATING_MAP]]. "
            "Then inventory → verify → reuse/connect → test → activate only within effective authority.\n"
        )
    elif filename == "07-Health-and-Metrics.md":
        body = "No health claim is current without timestamped retrievable evidence. Record source, timestamp, result, and next check.\n"
    elif filename in OPERATOR_BRIDGE_FILES:
        note_name = filename[:-3]
        body = (
            "This is a generated bridge and is safe to replace. Do not record operator-owned evidence here.\n\n"
            f"Use [[{OPERATOR_NOTES_ROOT}/{aid}/{note_name}]] for durable runtime notes. "
            "That sibling operator-note tree is preserved across governed brain generations.\n"
        )
    else:
        raise SystemExit(f"unsupported agent home file: {filename}")
    return common + body



def _source_boundary() -> str:
    return (
        "## Source-of-truth boundary\n\n"
        "- GitHub: versioned law, policy, code, contracts, and deployment records.\n"
        "- Foundation VM: current runtime state, only when supported by timestamped evidence.\n"
        "- Obsidian: operational context, coordination, decisions, and evidence links.\n"
        "- Stop on conflict, stale evidence, secret exposure, or an unauthorized production action.\n"
    )


def _command_state_doc(title: str, purpose: str) -> str:
    return (
        f"# {title[:-3]}\n\n"
        f"{purpose}\n\n"
        "## Command state\n\n"
        "- Last verified timestamp: UNKNOWN — populate only from current retrievable evidence.\n"
        "- Responsible role: Obsidian Scribe, with the accountable runtime owner for verification.\n"
        "- State: UNKNOWN\n"
        "- Source-of-truth links: [[03-Control-Plane/DOMINION_OPERATING_MAP]], "
        "[[03-Control-Plane/RUNTIME_ALIGNMENT]], "
        "[Execution Packet 001](https://github.com/dunkdee/dominion-ops/issues/92)\n"
        "- Next exact action: attach a current evidence reference, timestamp, and accountable owner.\n"
        "- Stop condition: stale or contradictory evidence, unclear authority, secret material, "
        "or a production mutation without separate approval.\n\n"
        + _source_boundary()
    )


def _architecture_doc(title: str, statement: str) -> str:
    return (
        f"# {title}\n\n"
        f"{statement}\n\n"
        "- State: UNKNOWN until reconciled with current evidence.\n"
        "- Last verified timestamp: UNKNOWN\n"
        "- Responsible role: Infrastructure Operator and QA and Evidence Auditor\n"
        "- Next exact action: link a timestamped inventory or verification record.\n"
        "- Stop condition: any conflict with GitHub governance or current runtime evidence.\n\n"
        + _source_boundary()
    )


def _evidence_doc(title: str, url: str) -> str:
    return (
        f"# {title}\n\n"
        f"- Canonical evidence link: [{title}]({url})\n"
        "- Snapshot state: UNKNOWN — retrieve the current GitHub state before relying on it.\n"
        "- Last verified timestamp: UNKNOWN\n"
        "- Responsible role: QA and Evidence Auditor\n"
        "- Next exact action: record the immutable commit, run, manifest, or issue evidence used.\n"
        "- Stop condition: changed head SHA, stale status, missing artifact, or contradictory runtime evidence.\n\n"
        + _source_boundary()
    )


def _operations_doc(title: str, statement: str) -> str:
    return (
        f"# {title}\n\n"
        f"{statement}\n\n"
        "- State: UNKNOWN\n"
        "- Last verified timestamp: UNKNOWN\n"
        "- Responsible role: Infrastructure Operator\n"
        "- Evidence links: [Execution Packet 001](https://github.com/dunkdee/dominion-ops/issues/92), "
        "[Archive Repair](https://github.com/dunkdee/dominion-ops/issues/93)\n"
        "- Next exact action: attach a current inventory, checksum, restore test, or capacity record.\n"
        "- Stop condition: count, size, checksum, path, authority, or freshness mismatch.\n\n"
        + _source_boundary()
    )


def _service_doc(name: str, purpose: str) -> str:
    return (
        f"# {name}\n\n"
        f"- Canonical service name: {name}\n"
        f"- Purpose: {purpose}\n"
        "- Accountable owner: UNKNOWN\n"
        "- Lifecycle state: UNKNOWN\n"
        "- Repository path: UNKNOWN\n"
        "- VM path: UNKNOWN\n"
        "- Deployment identity and exact SHA: UNKNOWN\n"
        "- Container or systemd identity: UNKNOWN\n"
        "- Ports, routes, and health checks: UNKNOWN\n"
        "- Dependencies and dependents: UNKNOWN\n"
        "- Secrets boundary: secret values are prohibited; record only protected-secret identifiers.\n"
        "- Monitoring and alert path: UNKNOWN\n"
        "- Backup and restore method: UNKNOWN\n"
        "- Rollback method: UNKNOWN\n"
        "- Last verified date: UNKNOWN\n"
        "- Current incidents or blockers: UNKNOWN\n"
        "- Next exact action: attach current runtime inventory and accountable-owner evidence.\n"
        "- Evidence links: [[03-Control-Plane/RUNTIME_ALIGNMENT]], "
        "[Execution Packet 001](https://github.com/dunkdee/dominion-ops/issues/92)\n\n"
        + _source_boundary()
    )


def _render_operational_notes(target: Path) -> None:
    for filename, purpose in COMMAND_STATE_NOTES:
        _atomic_write(
            target / "14-Daily-State" / filename,
            _command_state_doc(filename, purpose),
        )
    for relative, title, statement in ARCHITECTURE_NOTES:
        _atomic_write(target / relative, _architecture_doc(title, statement))
    for relative, title, url in EVIDENCE_NOTES:
        _atomic_write(target / relative, _evidence_doc(title, url))
    for relative, title, statement in OPERATIONS_NOTES:
        _atomic_write(target / relative, _operations_doc(title, statement))
    for filename, name, purpose in SERVICE_NOTES:
        _atomic_write(
            target / "06-Operations" / "Services" / filename,
            _service_doc(name, purpose),
        )

def _iter_output_files(target: Path) -> Iterable[Path]:
    for path in sorted(target.rglob("*")):
        if path.is_file() and not path.is_symlink():
            yield path


def render(target: Path) -> dict:
    target = target.expanduser().resolve(strict=False)
    if target.exists() or target.is_symlink():
        raise SystemExit("brain generation target must not already exist")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=False, exist_ok=False)
    try:
        registry = json.loads(_require_source(REGISTRY))
        authority = json.loads(_require_source(AUTHORITY))
        if not isinstance(registry, dict) or not isinstance(registry.get("agents"), list) or not registry["agents"]:
            raise SystemExit("agent registry is empty or malformed")
        if not isinstance(authority, dict) or authority.get("default_behavior") != "deny":
            raise SystemExit("authority matrix is empty, malformed, or not default-deny")

        seen = set()
        for agent in registry["agents"]:
            if not isinstance(agent, dict):
                raise SystemExit("agent registry contains a non-object entry")
            aid = _validate_agent_id(agent.get("id"))
            if aid in seen:
                raise SystemExit(f"duplicate agent id in governed registry: {aid}")
            seen.add(aid)

        for directory in ROOT_DIRS:
            (target / directory).mkdir(parents=True, exist_ok=True)

        # Canonical startup order from DOMINION_OPERATING_MAP.md.
        _copy_governed(target, "00-Constitution/SYSTEM_CONSTITUTION.md", SYSTEM_CONSTITUTION)
        _copy_governed(target, "00-Constitution/STATE.md", STATE)
        _copy_governed(target, "00-Constitution/REPOSITORY_README.md", REPOSITORY_README)
        _copy_governed(target, "04-Agents/REGISTRY.md", REGISTRY)
        _copy_governed(target, "01-Founder-Authority/AUTHORITY_MATRIX.md", AUTHORITY)
        _copy_governed(target, "02-Five-Council/FIVE_COUNCIL_POLICY.md", FIVE_COUNCIL)
        _copy_governed(target, "13-Learning/INCIDENT_LEARNING_POLICY.md", INCIDENT_LEARNING)
        _copy_governed(target, "05-Verticals/VERTICALS.md", VERTICALS)
        _copy_governed(target, "03-Control-Plane/CONTROL_PLANE.md", CONTROL_PLANE)

        _copy_governed(target, "03-Control-Plane/DOMINION_OPERATING_MAP.md", OPERATING_MAP)
        _copy_governed(target, "03-Control-Plane/AGENT_OPERATIONS_STATE.md", AGENT_STATE)
        _copy_governed(target, "03-Control-Plane/RUNTIME_ALIGNMENT.md", RUNTIME_ALIGNMENT)
        _copy_governed(target, "03-Control-Plane/BRAIN_README.md", BRAIN_README)
        _copy_governed(target, "04-Agents/TEAM_CURRENT_STATE.md", TEAM_STATE)

        _render_operational_notes(target)

        for agent in registry["agents"]:
            aid = _validate_agent_id(agent.get("id"))
            home = target / "04-Agents" / aid
            if home.exists() or home.is_symlink():
                raise SystemExit(f"agent home collision: {aid}")
            home.mkdir(parents=False, exist_ok=False)
            for filename in AGENT_FILES:
                _atomic_write(home / filename, _agent_doc(agent, filename, authority))

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
            "schema": "dominion-brain-manifest-v2",
            "source": "dunkdee/dominion-ops",
            "source_revision": {
                "kind": "governed-source-set-sha256",
                "sha256": _source_digest(GOVERNED_SOURCES),
            },
            "agent_count": len(registry["agents"]),
            "operator_notes_root": OPERATOR_NOTES_ROOT,
            "files": manifest,
        }
        _atomic_write(target / "MANIFEST.json", json.dumps(manifest_doc, indent=2))
        return manifest_doc
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="Fresh staging directory for one Dominion-Brain generation")
    args = parser.parse_args()
    manifest = render(args.target)
    print(
        "BRAIN_RENDER=PASS "
        f"agents={manifest['agent_count']} files={len(manifest['files'])} "
        f"source_digest={manifest['source_revision']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())