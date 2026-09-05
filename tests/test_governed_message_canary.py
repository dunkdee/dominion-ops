from __future__ import annotations

import builtins
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "runtime" / "governed_message_canary.py"


def _load_canary_module():
    spec = importlib.util.spec_from_file_location("test_governed_message_canary_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _force_missing_dotenv(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dotenv" and name not in sys.modules:
            raise ImportError("No module named 'dotenv'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_load_runtime_env_installs_dotenv_shim_and_preserves_first_assignment(monkeypatch, tmp_path):
    canary = _load_canary_module()
    (tmp_path / "buddy_core").mkdir()
    (tmp_path / "conductor").mkdir()
    (tmp_path / "buddy_core" / ".env").write_text(
        "PRIMARY=buddy-core\nDUPLICATE=first\nDUPLICATE=second\n",
        encoding="utf-8",
    )
    (tmp_path / "conductor" / ".env").write_text("PRIMARY=conductor\nCONDUCTOR_ONLY=yes\n", encoding="utf-8")
    (tmp_path / ".env").write_text("HOME_ONLY=present\n", encoding="utf-8")

    saved = sys.modules.pop("dotenv", None)
    _force_missing_dotenv(monkeypatch)
    for key in ("PRIMARY", "DUPLICATE", "CONDUCTOR_ONLY", "HOME_ONLY"):
        monkeypatch.delenv(key, raising=False)
    canary.out.clear()
    try:
        canary.load_runtime_env(tmp_path)
        assert os.environ["PRIMARY"] == "buddy-core"
        assert os.environ["DUPLICATE"] == "first"
        assert os.environ["CONDUCTOR_ONLY"] == "yes"
        assert os.environ["HOME_ONLY"] == "present"
        assert "dotenv" in sys.modules
        assert "CANARY_DOTENV=SHIM" in canary.out
    finally:
        if saved is not None:
            sys.modules["dotenv"] = saved
        else:
            sys.modules.pop("dotenv", None)


def test_dotenv_shim_supports_override_for_runtime_imports(monkeypatch, tmp_path):
    canary = _load_canary_module()
    (tmp_path / "buddy_core").mkdir()
    (tmp_path / "conductor").mkdir()
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("OVERRIDE_ME=first\nOVERRIDE_ME=second\n", encoding="utf-8")

    saved = sys.modules.pop("dotenv", None)
    _force_missing_dotenv(monkeypatch)
    monkeypatch.delenv("OVERRIDE_ME", raising=False)
    try:
        canary.load_runtime_env(tmp_path)
        from dotenv import load_dotenv

        monkeypatch.setenv("OVERRIDE_ME", "existing")
        assert load_dotenv(dotenv_path=custom_env, override=False) is True
        assert os.environ["OVERRIDE_ME"] == "existing"
        assert load_dotenv(dotenv_path=custom_env, override=True) is True
        assert os.environ["OVERRIDE_ME"] == "second"
    finally:
        if saved is not None:
            sys.modules["dotenv"] = saved
        else:
            sys.modules.pop("dotenv", None)
