#!/usr/bin/env python3
"""Validate the canonical Buddy authority policy without external dependencies."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_REPAIR_SERVICES = {
    "dominion-buddy-web.service",
    "dominion-proposal-queue.service",
    "dominion-sentinel.service",
}
REQUIRED_EXTERNAL_CLASSES = {
    "PUBLISH",
    "OUTREACH_OR_MESSAGE",
    "SPEND_OR_MOVE_MONEY",
    "LIVE_TRADE",
    "SIGN_OR_FILE",
    "CHANGE_CREDENTIALS",
    "CHANGE_FIREWALL",
    "OPEN_PUBLIC_INGRESS",
    "ACTIVATE_QUARANTINED_AGENT",
}
REQUIRED_AUTH_SOURCES = {
    "DIRECT_FOUNDER_INSTRUCTION",
    "ACTIVE_STANDING_FOUNDER_POLICY",
}
REQUIRED_RECEIPT_FIELDS = {
    "authorization_reference",
    "scope",
    "result",
    "evidence",
    "rollback_or_remediation",
}

AUTOMATIC_TRIGGERS = {
    "push",
    "schedule",
    "workflow_run",
    "repository_dispatch",
    "pull_request_target",
}
PRODUCTION_MARKERS = (
    "VM_SSH_KEY",
    "appleboy/ssh-action",
    "self-hosted",
    "foundation-vm-production",
    "gcloud compute",
)
HIGH_RISK_AUTOMATIC_PATTERNS = {
    "systemd mutation": re.compile(
        r"\bsystemctl\s+(?:restart|start|stop|enable|disable|mask|unmask|daemon-reload)\b",
        re.IGNORECASE,
    ),
    "container mutation": re.compile(
        r"\bdocker(?:\s+compose)?\s+(?:up|down|restart|start|stop|rm|kill|build|pull|run|tag)\b",
        re.IGNORECASE,
    ),
    "direct main write": re.compile(r"\bgit\s+push\b", re.IGNORECASE),
    "workflow dispatch mutation": re.compile(r"\bgh\s+workflow\s+run\b", re.IGNORECASE),
    "external secret mutation": re.compile(
        r"\b(?:netlify\s+env:set|gh\s+secret\s+set)\b", re.IGNORECASE
    ),
    "repair/deploy script execution": re.compile(
        r"(?:^|[;&|]\s*|\n\s*)(?:[A-Z0-9_='\"$ {}.-]+\s+)?"
        r"(?:bash\s+)?(?:scripts/)?(?:activate|deploy|repair)[A-Za-z0-9_./-]*\.sh\b",
        re.IGNORECASE,
    ),
}
OBSERVER_FORBIDDEN_PATTERNS = {
    "systemd mutation": HIGH_RISK_AUTOMATIC_PATTERNS["systemd mutation"],
    "container mutation": HIGH_RISK_AUTOMATIC_PATTERNS["container mutation"],
    "Git state mutation": re.compile(
        r"\bgit\s+(?:merge|push|reset|checkout|pull|update-ref)\b", re.IGNORECASE
    ),
    "cloud mutation": re.compile(
        r"\bgcloud\b[^\n]*(?:\bcreate\b|\bdelete\b|\bupdate\b|\badd-iam-policy-binding\b)",
        re.IGNORECASE,
    ),
    "configuration rewrite": re.compile(
        r"(?:\bsed\s+-i\b|\bsudo\s+tee\b)", re.IGNORECASE
    ),
    "write-method request": re.compile(
        r"\bcurl\b[^\n]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b",
        re.IGNORECASE,
    ),
}
ACTION_USES_RE = re.compile(
    r"^\\s*uses:\\s*([^@\\s]+)@([^\\s#]+)",
    re.MULTILINE,
)


class PolicyError(ValueError):
    """Raised when the policy violates a canonical invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{name} must be an object")
    return value


def _set(value: Any, name: str) -> set[str]:
    _require(isinstance(value, list), f"{name} must be an array")
    _require(all(isinstance(item, str) and item for item in value), f"{name} must contain non-empty strings")
    _require(len(value) == len(set(value)), f"{name} must not contain duplicates")
    return set(value)


def validate(policy: dict[str, Any]) -> None:
    _require(policy.get("schema") == "dominion-buddy-authority-v1", "schema mismatch")

    identity = _mapping(policy.get("identity"), "identity")
    _require(identity.get("agent_id") == "buddy", "identity.agent_id must be buddy")
    _require(identity.get("role") == "PRIMARY_PERSONAL_AI", "Buddy must be PRIMARY_PERSONAL_AI")
    _require(identity.get("principal") == "Dewayne Singleton", "principal mismatch")
    _require(identity.get("authority_model") == "FOUNDER_DIRECTED", "authority must be FOUNDER_DIRECTED")

    modes = _mapping(policy.get("operating_modes"), "operating_modes")
    expected_modes = {
        "learning": "ENABLED",
        "evolution": "PROPOSE_TEST_VERSION_ROLLBACK",
        "delegation": "ENABLED",
        "self_repair": "ENABLED",
        "external_actions": "FOUNDER_AUTHORIZED",
    }
    _require(modes == expected_modes, "operating_modes do not match the canonical Buddy model")

    auth = _mapping(policy.get("authorization"), "authorization")
    _require(_set(auth.get("accepted_sources"), "authorization.accepted_sources") == REQUIRED_AUTH_SOURCES,
             "authorization sources must be direct or standing Founder authorization")
    _require(auth.get("must_not_infer_authorization") is True, "inferred authorization must be prohibited")
    _require(auth.get("must_not_self_expand_authority") is True, "self-expanded authority must be prohibited")

    repair = _mapping(policy.get("self_repair"), "self_repair")
    _require(_set(repair.get("allowed_services"), "self_repair.allowed_services") == REQUIRED_REPAIR_SERVICES,
             "self-repair service allowlist changed")
    _require(isinstance(repair.get("max_attempts"), int) and 1 <= repair["max_attempts"] <= 3,
             "self_repair.max_attempts must be between 1 and 3")
    _require(isinstance(repair.get("cooldown_seconds"), int) and repair["cooldown_seconds"] >= 60,
             "self_repair.cooldown_seconds must be at least 60")
    _require(repair.get("independent_verifier") == "sentinel", "Sentinel must verify repair completion")
    _require(repair.get("on_exhaustion") == "STOP_AND_REPORT_BLOCKED", "repair must fail blocked")
    _require(repair.get("scope_expansion_requires_founder_authorization") is True,
             "repair scope expansion must require Founder authorization")

    evolution = _mapping(policy.get("evolution"), "evolution")
    _require(evolution.get("inference_must_be_labeled") is True, "agent inference must be labeled")
    founder_review = _set(evolution.get("founder_authorization_required_for"),
                          "evolution.founder_authorization_required_for")
    _require({"IDENTITY_CHANGE", "AUTHORITY_CHANGE", "EXTERNAL_REPRESENTATION_CHANGE"} <= founder_review,
             "identity, authority, and representation changes require Founder authorization")

    external = _mapping(policy.get("external_actions"), "external_actions")
    _require(external.get("mode") == "FOUNDER_AUTHORIZED", "external actions must be FOUNDER_AUTHORIZED")
    _require(_set(external.get("classes"), "external_actions.classes") == REQUIRED_EXTERNAL_CLASSES,
             "external action classes changed")
    _require(external.get("receipt_required") is True, "external action receipts are required")
    _require(_set(external.get("receipt_fields"), "external_actions.receipt_fields") == REQUIRED_RECEIPT_FIELDS,
             "external action receipt fields changed")

    representation = _mapping(policy.get("representation"), "representation")
    _require(representation.get("may_act_in_founder_style") is True, "Buddy must be allowed to act in Founder style")
    _require(representation.get("may_claim_founder_legal_identity") is False,
             "Buddy must not claim the Founder's legal identity")

    audit = _mapping(policy.get("audit"), "audit")
    _require(audit.get("append_only") is True, "audit records must be append-only")
    _require(audit.get("redact_secrets_and_personal_data") is True, "audit records must redact sensitive data")
    _require(audit.get("self_report_is_not_completion_evidence") is True,
             "self-report must not be completion evidence")

    conformance = _mapping(policy.get("live_conformance"), "live_conformance")
    _require(conformance.get("status") in {"UNVERIFIED", "VERIFIED"}, "invalid live conformance status")
    if conformance.get("source_state") == "VM_ONLY_UNRECONCILED":
        _require(conformance.get("status") == "UNVERIFIED",
                 "VM-only unreconciled source cannot be marked VERIFIED")

    autonomy = _mapping(policy.get("autonomy_control"), "autonomy_control")
    _require(autonomy.get("schema") == "dominion-autonomy-control-v1",
             "autonomy_control schema mismatch")
    _require(_mapping(autonomy.get("authority"), "autonomy_control.authority").get(
        "default_on_uncertainty") == "STOP_AND_REPORT_BLOCKED",
        "autonomy uncertainty must stop and report blocked")
    lanes = _mapping(autonomy.get("lanes"), "autonomy_control.lanes")
    _require(set(lanes) == {
        "ci_validation",
        "runtime_observation",
        "buddy_bounded_self_repair",
        "founder_approved_apply",
    }, "autonomy lanes changed")
    bounded = _mapping(lanes.get("buddy_bounded_self_repair"),
                       "autonomy_control.lanes.buddy_bounded_self_repair")
    _require(_set(bounded.get("allowed_services"),
                  "autonomy_control buddy services") == REQUIRED_REPAIR_SERVICES,
             "autonomy Buddy repair service allowlist changed")
    _require(bounded.get("max_attempts") == repair.get("max_attempts"),
             "autonomy and Buddy max attempts disagree")
    _require(bounded.get("cooldown_seconds") == repair.get("cooldown_seconds"),
             "autonomy and Buddy cooldown disagree")
    evidence = autonomy.get("online_evidence_fields")
    _require(isinstance(evidence, list) and len(evidence) == 9 and len(set(evidence)) == 9,
             "online evidence definition must contain nine unique fields")


def _on_block(text: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.match(r'^(?:on|"on"|\'on\')\s*:', line)), None)
    if start is None:
        return ""
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        block.append(line)
    return "\n".join(block)


def workflow_triggers(text: str) -> set[str]:
    block = _on_block(text)
    if not block:
        return set()
    triggers = set(re.findall(
        r"^\s{2}(push|pull_request|pull_request_target|schedule|workflow_dispatch|"
        r"workflow_run|repository_dispatch|workflow_call)\s*:",
        block,
        flags=re.MULTILINE,
    ))
    first = block.splitlines()[0]
    if "[" in first or "{" in first:
        for candidate in (
            "push", "pull_request", "pull_request_target", "schedule",
            "workflow_dispatch", "workflow_run", "repository_dispatch",
            "workflow_call",
        ):
            if re.search(rf"\b{re.escape(candidate)}\b", first):
                triggers.add(candidate)
    return triggers


def _on_has_exact_path(text: str, relative: str) -> bool:
    return re.search(
        rf"^\s*-\s*['\"]?{re.escape(relative)}['\"]?\s*$",
        _on_block(text),
        flags=re.MULTILINE,
    ) is not None


def workflow_job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^jobs\s*:\s*$", line)), None)
    if start is None:
        return {}
    headers: list[tuple[int, str]] = []
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        match = re.match(r"^\s{2}([A-Za-z0-9_-]+)\s*:\s*$", line)
        if match:
            headers.append((index, match.group(1)))
    result: dict[str, str] = {}
    for position, (index, name) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        result[name] = "\n".join(lines[index:end])
    return result


def _missing_founder_gate(block: str, token: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", block)
    required = (
        "github.event_name == 'workflow_dispatch'",
        f"inputs.confirm == '{token}'",
        "inputs.commit_sha == github.sha",
        "github.ref == 'refs/heads/main'",
    )
    return [condition for condition in required if condition not in normalized]


def _pattern_hits(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    return [name for name, pattern in patterns.items() if pattern.search(text)]


def _unpinned_actions(text: str) -> list[str]:
    return [
        f"{action}@{reference}"
        for action, reference in ACTION_USES_RE.findall(text)
        if re.fullmatch(r"[0-9a-fA-F]{40}", reference) is None
    ]


def _service_names(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Za-z0-9_-]+\.service\b", text))


def autonomy_workflow_errors(root: Path, policy: dict[str, Any]) -> list[str]:
    autonomy = _mapping(policy.get("autonomy_control"), "autonomy_control")
    errors: list[str] = []

    manual = _mapping(autonomy.get("manual_only_workflows"),
                      "autonomy_control.manual_only_workflows")
    guarded = _mapping(autonomy.get("guarded_jobs"),
                       "autonomy_control.guarded_jobs")
    approved = _mapping(autonomy.get("approved_automatic_mutators"),
                        "autonomy_control.approved_automatic_mutators")

    for relative, token in manual.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: manual-only workflow missing")
            continue
        text = path.read_text(encoding="utf-8")
        triggers = workflow_triggers(text)
        if triggers != {"workflow_dispatch"}:
            errors.append(f"{relative}: manual-only triggers={sorted(triggers)}")
        on = _on_block(text)
        if "confirm:" not in on or "commit_sha:" not in on:
            errors.append(f"{relative}: Founder inputs missing")
        jobs = workflow_job_blocks(text)
        if not jobs:
            errors.append(f"{relative}: jobs missing")
        for job, block in jobs.items():
            missing = _missing_founder_gate(block, str(token))
            if missing:
                errors.append(f"{relative} job {job}: gate missing {', '.join(missing)}")

    for relative, job_policy in guarded.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: guarded workflow missing")
            continue
        text = path.read_text(encoding="utf-8")
        if "workflow_dispatch" not in workflow_triggers(text):
            errors.append(f"{relative}: workflow_dispatch missing")
        on = _on_block(text)
        if "confirm:" not in on or "commit_sha:" not in on:
            errors.append(f"{relative}: guarded inputs missing")
        jobs = workflow_job_blocks(text)
        for job, token in _mapping(job_policy, f"{relative} guarded jobs").items():
            block = jobs.get(job)
            if block is None:
                errors.append(f"{relative}: guarded job {job} missing")
                continue
            missing = _missing_founder_gate(block, str(token))
            if missing:
                errors.append(f"{relative} job {job}: gate missing {', '.join(missing)}")

    lanes = _mapping(autonomy.get("lanes"), "autonomy_control.lanes")
    observer_path = Path(_mapping(lanes.get("runtime_observation"),
                                  "runtime_observation")["workflow"])
    observer = root / observer_path
    if not observer.is_file():
        errors.append(f"{observer_path}: observer missing")
    else:
        text = observer.read_text(encoding="utf-8")
        if workflow_triggers(text) != {"push", "schedule", "workflow_dispatch"}:
            errors.append(f"{observer_path}: observer triggers changed")
        if not _on_has_exact_path(text, observer_path.as_posix()):
            errors.append(f"{observer_path}: push not limited to own path")
        for hit in _pattern_hits(text, OBSERVER_FORBIDDEN_PATTERNS):
            errors.append(f"{observer_path}: forbidden observer {hit}")
        for action in _unpinned_actions(text):
            errors.append(f"{observer_path}: unpinned action {action}")
        for marker in (
            "RUNTIME_OBSERVER=", "CONTAINMENT_HOLD=", "allow-ops-dashboard",
            "allow-twilio-router", "127.0.0.1:5070/buddy",
        ):
            if marker not in text:
                errors.append(f"{observer_path}: evidence marker missing {marker}")

    bounded = _mapping(lanes.get("buddy_bounded_self_repair"),
                       "buddy_bounded_self_repair")
    buddy_path = Path(bounded["workflow"])
    buddy = root / buddy_path
    if not buddy.is_file():
        errors.append(f"{buddy_path}: bounded Buddy workflow missing")
    else:
        text = buddy.read_text(encoding="utf-8")
        if workflow_triggers(text) != {"push", "schedule", "workflow_dispatch"}:
            errors.append(f"{buddy_path}: Buddy self-heal triggers changed")
        if not _on_has_exact_path(text, buddy_path.as_posix()):
            errors.append(f"{buddy_path}: push not limited to own path")
        expected = set(bounded["allowed_services"])
        if _service_names(text) != expected:
            errors.append(f"{buddy_path}: Buddy service scope changed")
        if f"MAX_ATTEMPTS={bounded['max_attempts']}" not in text:
            errors.append(f"{buddy_path}: max attempts mismatch")
        if f"COOLDOWN_SECONDS={bounded['cooldown_seconds']}" not in text:
            errors.append(f"{buddy_path}: cooldown mismatch")
        if 'sudo systemctl restart "$unit"' not in text:
            errors.append(f"{buddy_path}: bounded restart missing")
        buddy_forbidden = {
            "source patching": re.compile(r"buddy_core|\bsed\s+-i\b|write_text\s*\(", re.I),
            "container control": re.compile(r"\bdocker\b", re.I),
            "cloud control": re.compile(r"\bgcloud\b", re.I),
            "Git mutation": re.compile(r"\bgit\s+(?:push|merge|reset|checkout|pull)\b", re.I),
            "non-local HTTP": re.compile(r"\bcurl\b[^\n]*https?://(?!127\.0\.0\.1|localhost)", re.I),
            "systemd scope expansion": re.compile(
                r"\bsystemctl\s+(?:enable|disable|mask|unmask|daemon-reload)\b", re.I),
        }
        for hit in _pattern_hits(text, buddy_forbidden):
            errors.append(f"{buddy_path}: forbidden Buddy operation {hit}")
        for marker in (
            "BUDDY_SELF_HEAL=NO_ACTION_HEALTHY", "BUDDY_SELF_HEAL=RECOVERED",
            "BUDDY_SELF_HEAL=BLOCKED_CIRCUIT_OPEN", "flock -n 9",
        ):
            if marker not in text:
                errors.append(f"{buddy_path}: repair marker missing {marker}")

    legacy = _mapping(autonomy.get("legacy_buddy_exception"),
                      "autonomy_control.legacy_buddy_exception")
    legacy_path = Path(legacy["workflow"])
    legacy_text = (root / legacy_path).read_text(encoding="utf-8") if (root / legacy_path).is_file() else ""
    if not legacy_text:
        errors.append(f"{legacy_path}: legacy Buddy exception missing")
    else:
        if workflow_triggers(legacy_text) != {"push", "workflow_dispatch"}:
            errors.append(f"{legacy_path}: legacy trigger scope changed")
        if not _on_has_exact_path(legacy_text, legacy_path.as_posix()):
            errors.append(f"{legacy_path}: push not limited to own path")
        if _service_names(legacy_text) != REQUIRED_REPAIR_SERVICES:
            errors.append(f"{legacy_path}: legacy Buddy service scope expanded")

    workflow_dir = root / ".github/workflows"
    for path in sorted(workflow_dir.glob("*.y*ml")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if not workflow_triggers(text).intersection(AUTOMATIC_TRIGGERS):
            continue
        if relative in approved:
            for action in _unpinned_actions(text):
                errors.append(f"{relative}: unpinned approved automatic action {action}")
            continue
        if relative in guarded or relative in manual:
            continue
        hits = _pattern_hits(text, HIGH_RISK_AUTOMATIC_PATTERNS)
        production = any(marker in text for marker in PRODUCTION_MARKERS)
        direct_dispatch = "gh workflow run" in text.lower() or "git push" in text.lower()
        if hits and (production or direct_dispatch):
            errors.append(f"{relative}: unapproved automatic mutation {', '.join(hits)}")

    return errors


def load_and_validate(path: Path, root: Path | None = None) -> None:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy: {exc}") from exc
    _require(isinstance(policy, dict), "policy root must be an object")
    validate(policy)
    if root is not None:
        errors = autonomy_workflow_errors(root.resolve(), policy)
        _require(not errors, "AUTONOMY_CONTROL=FAIL " + "; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        load_and_validate(args.policy, args.root)
    except PolicyError as exc:
        print(f"BUDDY_POLICY=FAIL reason={exc}")
        return 1
    print("BUDDY_POLICY=PASS")
    print("AUTONOMY_CONTROL=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
