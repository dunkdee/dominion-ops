from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "runtime" / "remediate_watchmen_state_boundary.sh"
DURABLE = {
    "watchmen_hmac.key": b"k" * 64 + b"\n",
    "watchmen_audit.log": b'{"seq":1,"event":"existing"}\n',
    "watchmen_chain.json": b'{"last_seq":1,"last_hash":"abc"}\n',
}


def _env(home: Path, target: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["DOMINION_WATCHMEN_LEGACY_STATE_DIR"] = str(home / ".dominion" / "watchmen")
    env["DOMINION_WATCHMEN_MACHINE_STATE_DIR"] = str(target)
    return env


def _seed_legacy(home: Path) -> Path:
    legacy = home / ".dominion" / "watchmen"
    legacy.mkdir(parents=True)
    for name, payload in DURABLE.items():
        (legacy / name).write_bytes(payload)
    (legacy / "watchmen_audit.lock").write_text("stale-lock\n", encoding="utf-8")
    return legacy


def _run(home: Path, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=_env(home, target),
        text=True,
        capture_output=True,
        check=False,
    )


def test_watchmen_state_migration_preserves_chain_and_is_idempotent(tmp_path: Path):
    home = tmp_path / "home"
    target = tmp_path / "machine-local" / "watchmen"
    legacy = _seed_legacy(home)

    first = _run(home, target)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "WATCHMEN_STATE_MIGRATION=PASS preserved_machine_local_state" in first.stdout
    assert legacy.is_symlink()
    assert legacy.resolve() == target.resolve()

    for name, payload in DURABLE.items():
        assert (target / name).read_bytes() == payload
    assert not (target / "watchmen_audit.lock").exists()

    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o700
        for name in DURABLE:
            assert stat.S_IMODE((target / name).stat().st_mode) == 0o600

    second = _run(home, target)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "WATCHMEN_STATE_MIGRATION=PASS already_external" in second.stdout
    for name, payload in DURABLE.items():
        assert (target / name).read_bytes() == payload


def test_watchmen_state_migration_fails_closed_on_conflicting_target(tmp_path: Path):
    home = tmp_path / "home"
    target = tmp_path / "machine-local" / "watchmen"
    legacy = _seed_legacy(home)
    target.mkdir(parents=True)
    (target / "watchmen_hmac.key").write_bytes(b"different-key-material" * 4)

    result = _run(home, target)

    assert result.returncode != 0
    assert "WATCHMEN_STATE_MIGRATION=FAIL conflicting_watchmen_hmac.key" in result.stdout
    assert legacy.is_dir()
    assert not legacy.is_symlink()
    assert (legacy / "watchmen_hmac.key").read_bytes() == DURABLE["watchmen_hmac.key"]


def test_watchmen_state_migration_rejects_target_inside_home(tmp_path: Path):
    home = tmp_path / "home"
    _seed_legacy(home)
    target = home / "machine-local" / "watchmen"

    result = _run(home, target)

    assert result.returncode == 2
    assert "WATCHMEN_STATE_MIGRATION=FAIL target_inside_home" in result.stdout
