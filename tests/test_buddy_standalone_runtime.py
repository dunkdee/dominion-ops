from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_buddy_bridge_bootstraps_canonical_repo_before_revenue_import():
    source = (ROOT / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
    bootstrap = source.index("DOMINION_REPO_ROOT")
    revenue_import = source.index("from core.revenue_runtime import")
    assert bootstrap < revenue_import
    assert 'Path.home() / "dominion-ops"' in source
    assert "sys.path.insert(0" in source


def test_standalone_bootstrap_does_not_hardcode_secrets():
    source = (ROOT / "buddy_core" / "buddy_bridge_api.py").read_text(encoding="utf-8")
    assert "DOMINION_REPO_ROOT" in source
    assert "API_KEY=" not in source
    assert "SECRET_KEY=" not in source
