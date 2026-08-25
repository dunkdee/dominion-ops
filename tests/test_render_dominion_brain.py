import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_dominion_brain.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_dominion_brain", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_render_creates_home_for_every_registered_agent(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    manifest = module.render(target)
    registry = json.loads((ROOT / "agents" / "registry.json").read_text(encoding="utf-8"))

    assert manifest["agent_count"] == len(registry["agents"])
    assert manifest["source_revision"]["kind"] == "governed-source-set-sha256"
    assert len(manifest["source_revision"]["sha256"]) == 64
    assert (target / "MANIFEST.json").is_file()
    assert (target / "00-Constitution" / "SYSTEM_CONSTITUTION.md").is_file()
    assert (target / "00-Constitution" / "STATE.md").is_file()
    assert (target / "00-Constitution" / "REPOSITORY_README.md").is_file()
    assert (target / "04-Agents" / "REGISTRY.md").is_file()
    assert (target / "01-Founder-Authority" / "AUTHORITY_MATRIX.md").is_file()
    assert (target / "02-Five-Council" / "FIVE_COUNCIL_POLICY.md").is_file()
    assert (target / "13-Learning" / "INCIDENT_LEARNING_POLICY.md").is_file()
    assert (target / "05-Verticals" / "VERTICALS.md").is_file()
    assert (target / "03-Control-Plane" / "CONTROL_PLANE.md").is_file()
    assert (target / "03-Control-Plane" / "DOMINION_OPERATING_MAP.md").is_file()
    assert (target / "04-Agents" / "TEAM_CURRENT_STATE.md").is_file()

    for agent in registry["agents"]:
        home = target / "04-Agents" / agent["id"]
        assert home.is_dir()
        assert sorted(p.name for p in home.glob("*.md")) == sorted(module.AGENT_FILES)


def test_manifest_hashes_match_rendered_files(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    manifest = module.render(target)

    for item in manifest["files"]:
        raw = (target / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert len(raw) == item["bytes"]


def test_source_revision_is_deterministic(tmp_path):
    module = load_renderer()
    one = module.render(tmp_path / "one")
    two = module.render(tmp_path / "two")
    assert one["source_revision"] == two["source_revision"]


def test_renderer_does_not_read_environment_secrets(tmp_path, monkeypatch):
    module = load_renderer()
    monkeypatch.setenv("EMAIL_PASSWORD", "MUST_NOT_APPEAR_IN_BRAIN")
    target = tmp_path / "Dominion-Brain"
    module.render(target)
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in target.rglob("*")
        if path.is_file()
    )
    assert "MUST_NOT_APPEAR_IN_BRAIN" not in combined


def test_renderer_rejects_existing_target_even_if_empty(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    target.mkdir()
    with pytest.raises(SystemExit, match="must not already exist"):
        module.render(target)


def test_renderer_rejects_symlink_target(tmp_path):
    module = load_renderer()
    real = tmp_path / "real"
    real.mkdir()
    target = tmp_path / "Dominion-Brain"
    target.symlink_to(real, target_is_directory=True)
    with pytest.raises(SystemExit, match="must not already exist"):
        module.render(target)


def test_malicious_agent_id_cannot_escape_target(tmp_path, monkeypatch):
    module = load_renderer()
    registry = json.loads(module.REGISTRY.read_text(encoding="utf-8"))
    registry["agents"][0]["id"] = "../../outside"
    malicious = tmp_path / "registry.json"
    malicious.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(module, "REGISTRY", malicious)
    target = tmp_path / "Dominion-Brain"
    with pytest.raises(SystemExit, match="unsafe agent id"):
        module.render(target)
    assert not (tmp_path / "outside").exists()
    assert not target.exists()


def test_authority_note_uses_effective_matrix_and_constraints(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)
    note = (target / "04-Agents" / "research" / "02-Authority.md").read_text(encoding="utf-8")
    assert "Effective governed action permissions" in note
    assert "`read_public_information`" in note
    assert "`respect_source_terms`" in note
    assert "descriptive, not independent authority" in note
    assert "Default behavior: `deny`" in note


def test_operator_owned_notes_are_external_bridges(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)
    bridge = (target / "04-Agents" / "research" / "08-Incidents-and-Lessons.md").read_text(encoding="utf-8")
    assert "Do not record operator-owned evidence here" in bridge
    assert "Dominion-Operator-Notes/research/08-Incidents-and-Lessons" in bridge
    assert not (target / module.OPERATOR_NOTES_ROOT).exists()


def test_dependency_links_resolve_to_rendered_governance_docs(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)
    deps = (target / "04-Agents" / "research" / "05-Dependencies.md").read_text(encoding="utf-8")
    expected = {
        "00-Constitution/SYSTEM_CONSTITUTION": target / "00-Constitution" / "SYSTEM_CONSTITUTION.md",
        "00-Constitution/STATE": target / "00-Constitution" / "STATE.md",
        "00-Constitution/REPOSITORY_README": target / "00-Constitution" / "REPOSITORY_README.md",
        "04-Agents/REGISTRY": target / "04-Agents" / "REGISTRY.md",
        "01-Founder-Authority/AUTHORITY_MATRIX": target / "01-Founder-Authority" / "AUTHORITY_MATRIX.md",
        "02-Five-Council/FIVE_COUNCIL_POLICY": target / "02-Five-Council" / "FIVE_COUNCIL_POLICY.md",
        "13-Learning/INCIDENT_LEARNING_POLICY": target / "13-Learning" / "INCIDENT_LEARNING_POLICY.md",
        "05-Verticals/VERTICALS": target / "05-Verticals" / "VERTICALS.md",
        "03-Control-Plane/CONTROL_PLANE": target / "03-Control-Plane" / "CONTROL_PLANE.md",
    }
    for link, path in expected.items():
        assert f"[[{link}]]" in deps
        assert path.is_file()


def test_failed_generation_is_cleaned_instead_of_published(tmp_path, monkeypatch):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    original = module._agent_doc
    calls = {"count": 0}

    def fail_mid_generation(agent, filename, authority):
        calls["count"] += 1
        if calls["count"] > 5:
            raise RuntimeError("synthetic failure")
        return original(agent, filename, authority)

    monkeypatch.setattr(module, "_agent_doc", fail_mid_generation)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        module.render(target)
    assert not target.exists()


def test_team_state_uses_constitutional_truth_vocabulary(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)
    state = (target / "04-Agents" / "TEAM_CURRENT_STATE.md").read_text(encoding="utf-8")
    assert "`UNKNOWN`" in state
    assert "result` must be `UNKNOWN`" in state
    assert "result` must be `unverified`" not in state


def test_work_order_94_operational_notes_exist_and_are_source_bound(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)

    command_fields = (
        "Last verified timestamp:",
        "Responsible role:",
        "Source-of-truth links:",
        "State:",
        "Next exact action:",
        "Stop condition:",
    )
    for filename, _ in module.COMMAND_STATE_NOTES:
        note = target / "14-Daily-State" / filename
        assert note.is_file()
        text = note.read_text(encoding="utf-8")
        for field in command_fields:
            assert field in text
        assert "UNKNOWN" in text

    required = [
        *(relative for relative, _, _ in module.ARCHITECTURE_NOTES),
        *(relative for relative, _, _ in module.EVIDENCE_NOTES),
        *(relative for relative, _, _ in module.OPERATIONS_NOTES),
    ]
    for relative in required:
        text = (target / relative).read_text(encoding="utf-8")
        assert "Source-of-truth boundary" in text
        assert "UNKNOWN" in text

    assert not (target / "Dominion").exists()


def test_priority_service_notes_use_complete_schema(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    module.render(target)

    fields = (
        "Canonical service name:",
        "Purpose:",
        "Accountable owner:",
        "Lifecycle state:",
        "Repository path:",
        "VM path:",
        "Deployment identity and exact SHA:",
        "Container or systemd identity:",
        "Ports, routes, and health checks:",
        "Dependencies and dependents:",
        "Secrets boundary:",
        "Monitoring and alert path:",
        "Backup and restore method:",
        "Rollback method:",
        "Last verified date:",
        "Current incidents or blockers:",
        "Next exact action:",
        "Evidence links:",
    )
    for filename, _, _ in module.SERVICE_NOTES:
        note = target / "06-Operations" / "Services" / filename
        assert note.is_file()
        text = note.read_text(encoding="utf-8")
        for field in fields:
            assert field in text
        assert "Source-of-truth boundary" in text


def test_legacy_setup_vault_is_non_mutating(tmp_path):
    vault = tmp_path / "legacy-vault"
    env = dict(os.environ, VAULT_PATH=str(vault))
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_vault.sh")],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    assert result.returncode == 2
    assert "LEGACY_VAULT_SETUP=RETIRED mutation=none" in result.stdout
    assert not vault.exists()
