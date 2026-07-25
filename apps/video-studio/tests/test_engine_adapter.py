import json

import pytest

from worker.engine_adapter import load_engine_spec


def _spec(**overrides):
    value = {
        "schema_version": 1,
        "engine_id": "approved-test-engine",
        "engine_version": "1.2.3",
        "license_status": "approved_for_intended_use",
        "license_reference": "governance/test-license-record.md",
        "commercial_use_verified": True,
        "command": [
            "renderer",
            "--portrait",
            "{portrait}",
            "--voice",
            "{voice}",
            "--output",
            "{output}",
            "--format",
            "{output_format}",
        ],
        "required_assets": ["portrait", "voice"],
        "supported_formats": ["vertical"],
        "timeout_seconds": 600,
    }
    value.update(overrides)
    return value


def _load(tmp_path, monkeypatch, value):
    path = tmp_path / "engine.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setenv("VIDEO_CLONE_ENGINE_SPEC", str(path))
    monkeypatch.delenv("VIDEO_CLONE_COMMAND", raising=False)
    monkeypatch.delenv("VIDEO_CLONE_ALLOW_UNAPPROVED_ENGINE", raising=False)
    return load_engine_spec()


def test_approved_engine_builds_argument_vector(tmp_path, monkeypatch):
    engine = _load(tmp_path, monkeypatch, _spec())
    command = engine.build_command(
        {
            "portrait": "/work/portrait.png",
            "voice": "/work/voice.wav",
            "source_video": "",
            "script_file": "/work/script.txt",
            "output_format": "vertical",
            "output": "/work/output.mp4",
        }
    )
    assert command == [
        "renderer",
        "--portrait",
        "/work/portrait.png",
        "--voice",
        "/work/voice.wav",
        "--output",
        "/work/output.mp4",
        "--format",
        "vertical",
    ]


def test_unapproved_engine_is_fail_closed(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="not approved"):
        _load(
            tmp_path,
            monkeypatch,
            _spec(license_status="blocked", commercial_use_verified=False),
        )


def test_unknown_placeholder_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Unknown engine command placeholders"):
        _load(
            tmp_path,
            monkeypatch,
            _spec(command=["renderer", "{portrait}", "{voice}", "{output}", "{secret}"]),
        )


def test_worker_rejects_unsupported_format(tmp_path, monkeypatch):
    engine = _load(tmp_path, monkeypatch, _spec())
    with pytest.raises(ValueError, match="does not support format"):
        engine.build_command(
            {
                "portrait": "/work/portrait.png",
                "voice": "/work/voice.wav",
                "source_video": "",
                "script_file": "/work/script.txt",
                "output_format": "landscape",
                "output": "/work/output.mp4",
            }
        )


def test_worker_rejects_missing_required_asset(tmp_path, monkeypatch):
    engine = _load(tmp_path, monkeypatch, _spec())
    with pytest.raises(ValueError, match="missing required assets: voice"):
        engine.build_command(
            {
                "portrait": "/work/portrait.png",
                "voice": "",
                "source_video": "",
                "script_file": "/work/script.txt",
                "output_format": "vertical",
                "output": "/work/output.mp4",
            }
        )
