from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "set_email_drip_runtime.py"


def load_module():
    spec = importlib.util.spec_from_file_location("set_email_drip_runtime", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def env_file(tmp_path: Path, body: str = "DRIP_SEND_MODE=hold\nSMTP_PASSWORD=DO_NOT_PRINT\nOTHER=value\n") -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_live_transition_changes_only_control_keys_and_preserves_metadata(tmp_path, capsys):
    module = load_module()
    path = env_file(tmp_path)
    before = path.stat()
    module.apply(path, "live", "hold")
    text = path.read_text(encoding="utf-8")
    assert "DRIP_SEND_MODE=live" in text
    assert "DRIP_LIVE_PREFLIGHT_OK=true" in text
    assert "DRIP_LIVE_AUTHORIZED_AT=" in text
    assert "SMTP_PASSWORD=DO_NOT_PRINT" in text
    assert "OTHER=value" in text
    after = path.stat()
    assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
        before.st_uid,
        before.st_gid,
        stat.S_IMODE(before.st_mode),
    )
    output = capsys.readouterr().out
    assert "DO_NOT_PRINT" not in output
    assert "mode=live" in output
    assert list(tmp_path.glob(".env.drip-live-*.bak"))


def test_hold_transition_clears_live_authorization(tmp_path):
    module = load_module()
    path = env_file(
        tmp_path,
        "DRIP_SEND_MODE=live\nDRIP_LIVE_PREFLIGHT_OK=true\nDRIP_LIVE_AUTHORIZED_AT=2026-08-09T12:00:00+00:00\nSECRET_TOKEN=DO_NOT_PRINT\n",
    )
    module.apply(path, "hold", "live")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "DRIP_SEND_MODE=hold" in lines
    assert "DRIP_LIVE_PREFLIGHT_OK=false" in lines
    assert "DRIP_LIVE_AUTHORIZED_AT=" in lines
    assert "SECRET_TOKEN=DO_NOT_PRINT" in lines


def test_duplicate_control_assignment_is_rejected(tmp_path):
    module = load_module()
    path = env_file(tmp_path, "DRIP_SEND_MODE=hold\nDRIP_SEND_MODE=live\n")
    with pytest.raises(SystemExit, match="ASSIGNMENTS_INVALID"):
        module.apply(path, "hold", "either")


def test_precondition_is_fail_closed(tmp_path):
    module = load_module()
    path = env_file(tmp_path)
    with pytest.raises(SystemExit, match="PRECONDITION_FAIL"):
        module.apply(path, "live", "live")
    assert "DRIP_SEND_MODE=hold" in path.read_text(encoding="utf-8")


def test_symlink_target_is_rejected(tmp_path):
    module = load_module()
    real = env_file(tmp_path)
    link = tmp_path / "linked.env"
    link.symlink_to(real)
    with pytest.raises(SystemExit, match="ENV_TARGET_INVALID"):
        module.apply(link, "hold", "either")


def test_idempotent_hold_does_not_expose_secret(tmp_path, capsys):
    module = load_module()
    path = env_file(
        tmp_path,
        "DRIP_SEND_MODE=hold\nDRIP_LIVE_PREFLIGHT_OK=false\nDRIP_LIVE_AUTHORIZED_AT=\nSMTP_PASSWORD=DO_NOT_PRINT\n",
    )
    module.apply(path, "hold", "hold")
    output = capsys.readouterr().out
    assert "idempotent=true" in output
    assert "DO_NOT_PRINT" not in output
