import importlib.util
import json
from pathlib import Path


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
    assert (target / "MANIFEST.json").is_file()
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
    import hashlib

    for item in manifest["files"]:
        raw = (target / item["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert len(raw) == item["bytes"]


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
