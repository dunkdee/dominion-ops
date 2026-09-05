from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

SOURCE = (
    pathlib.Path(__file__).parents[1]
    / "scripts"
    / "runtime"
    / "resolve_canary_expected_sha.py"
)

spec = importlib.util.spec_from_file_location("resolve_canary_expected_sha", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["resolve_canary_expected_sha"] = module
spec.loader.exec_module(module)


def test_explicit_sha_is_returned_as_is():
    sha = "117c84e5ab26ee34314365548655793eaf247dfd"
    assert module.resolve_expected_sha(sha) == sha


def test_deployed_mode_reads_sha_from_receipt():
    receipt = {"release_sha": "fd42d1f5d1fbf82b23d7d15f3fd56e8e18a51c71"}
    assert module.resolve_expected_sha("DEPLOYED", receipt) == receipt["release_sha"]


def test_deployed_mode_fails_closed_on_missing_or_invalid_sha():
    with pytest.raises(ValueError):
        module.resolve_expected_sha("DEPLOYED", {})
    with pytest.raises(ValueError):
        module.resolve_expected_sha("DEPLOYED", {"release_sha": "not-a-sha"})


def test_cli_rejects_invalid_receipt_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["resolve_canary_expected_sha.py", "--expected-sha", "DEPLOYED", "--receipt-stdin"])
    monkeypatch.setattr(sys, "stdin", type("In", (), {"read": staticmethod(lambda: "{bad json}")})())
    rc = module.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "Invalid deployed_release.json payload" in captured.err


def test_cli_emits_resolved_sha_from_stdin(monkeypatch, capsys):
    sha = "8bf53df836ca9b1d056b7888be715c9d7f9179fc"
    payload = json.dumps({"release_sha": sha})
    monkeypatch.setattr(sys, "argv", ["resolve_canary_expected_sha.py", "--expected-sha", "DEPLOYED", "--receipt-stdin"])
    monkeypatch.setattr(sys, "stdin", type("In", (), {"read": staticmethod(lambda: payload)})())
    rc = module.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == sha
