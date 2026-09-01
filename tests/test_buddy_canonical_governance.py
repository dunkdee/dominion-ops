from pathlib import Path

from buddy_core.core import brain_router


ROOT = Path(__file__).resolve().parents[1]


def test_elite_protocol_is_non_bypassable_for_custom_systems():
    custom = "Narrow specialist instruction."
    composed = brain_router._compose_system(custom)
    assert "ELITE REASONING PROTOCOL" in composed
    assert "Founder Operating Context" in composed
    assert "Capability Maximization Doctrine" in composed
    assert custom in composed
    assert composed.index("ELITE REASONING PROTOCOL") < composed.index(custom)


def test_youtube_specialist_uses_canonical_system_composition():
    source = (ROOT / "apps" / "youtube" / "script_generator.py").read_text(encoding="utf-8")
    assert "_compose_system" in source
    assert "claude-fable-5" not in source.lower()
    assert "fable 5" not in source.lower()


def test_buddy_core_and_youtube_paths_have_no_fable_reference():
    roots = [ROOT / "buddy_core", ROOT / "apps" / "youtube"]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if "fable" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
