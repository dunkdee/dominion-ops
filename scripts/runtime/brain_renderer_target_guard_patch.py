#!/usr/bin/env python3
from pathlib import Path

renderer = Path('scripts/render_dominion_brain.py')
tests_path = Path('tests/test_render_dominion_brain.py')
text = renderer.read_text(encoding='utf-8')
old = '''def render(target: Path) -> dict:
    registry = json.loads(_require_source(REGISTRY))
    if not isinstance(registry.get("agents"), list) or not registry["agents"]:
        raise SystemExit("agent registry is empty or malformed")

    target.mkdir(parents=True, exist_ok=True)
'''
new = '''def render(target: Path) -> dict:
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

'''
count = text.count(old)
if count != 1:
    raise SystemExit(f'render target anchor count={count}')
renderer.write_text(text.replace(old, new, 1), encoding='utf-8', newline='\n')

tests = tests_path.read_text(encoding='utf-8')
if 'def test_renderer_rejects_nonempty_target' not in tests:
    tests += r'''


def test_renderer_rejects_nonempty_target(tmp_path):
    module = load_renderer()
    target = tmp_path / "Dominion-Brain"
    target.mkdir()
    (target / "ungoverned.md").write_text("must not be incorporated", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit, match="must be empty"):
        module.render(target)


def test_renderer_rejects_symlink_target(tmp_path):
    module = load_renderer()
    real = tmp_path / "real"
    real.mkdir()
    target = tmp_path / "Dominion-Brain"
    target.symlink_to(real, target_is_directory=True)
    import pytest
    with pytest.raises(SystemExit, match="must not be a symlink"):
        module.render(target)
'''
    tests_path.write_text(tests, encoding='utf-8', newline='\n')
