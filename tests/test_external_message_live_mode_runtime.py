from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "runtime" / "enable_governed_external_message_live_mode.sh"


def _run(target: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["BUDDY_EXTERNAL_MESSAGE_ENV_FILE"] = str(target)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_live_mode_upsert_preserves_unrelated_values_and_redacts_output(tmp_path: Path):
    target = tmp_path / "buddy_core" / ".env"
    target.parent.mkdir(parents=True)
    target.write_text(
        "SMTP_PASSWORD=do-not-print-this-secret\n"
        "OTHER_SETTING=preserve-me\n"
        "BUDDY_EXTERNAL_MESSAGE_MODE=hold\n",
        encoding="utf-8",
    )

    result = _run(target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "EXTERNAL_MESSAGE_MODE=LIVE"
    assert "do-not-print-this-secret" not in result.stdout + result.stderr
    content = target.read_text(encoding="utf-8")
    assert "SMTP_PASSWORD=do-not-print-this-secret\n" in content
    assert "OTHER_SETTING=preserve-me\n" in content
    assert content.count("BUDDY_EXTERNAL_MESSAGE_MODE=live") == 1
    assert "BUDDY_EXTERNAL_MESSAGE_MODE=hold" not in content
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_live_mode_is_idempotent_and_collapses_duplicate_mode_entries(tmp_path: Path):
    target = tmp_path / "buddy_core" / ".env"
    target.parent.mkdir(parents=True)
    target.write_text(
        "BUDDY_EXTERNAL_MESSAGE_MODE=hold\n"
        "export BUDDY_EXTERNAL_MESSAGE_MODE=live\n"
        "SMTP_HOST=mail.example.test\n",
        encoding="utf-8",
    )

    first = _run(target)
    snapshot = target.read_bytes()
    second = _run(target)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert target.read_bytes() == snapshot
    content = target.read_text(encoding="utf-8")
    assert content.count("BUDDY_EXTERNAL_MESSAGE_MODE=live") == 1
    assert "BUDDY_EXTERNAL_MESSAGE_MODE=hold" not in content
    assert "SMTP_HOST=mail.example.test\n" in content


def test_live_mode_creates_missing_env_file(tmp_path: Path):
    target = tmp_path / "buddy_core" / ".env"

    result = _run(target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text(encoding="utf-8") == "BUDDY_EXTERNAL_MESSAGE_MODE=live\n"
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_live_mode_fails_closed_when_target_is_not_a_file(tmp_path: Path):
    target = tmp_path / "buddy_core" / ".env"
    target.mkdir(parents=True)

    result = _run(target)

    assert result.returncode == 2
    assert "EXTERNAL_MESSAGE_MODE=FAIL target_not_file" in result.stdout
