"""Validated renderer adapter for detachable Dominion Video Studio workers."""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Mapping

_ALLOWED_PLACEHOLDERS = {
    "portrait",
    "voice",
    "source_video",
    "script_file",
    "output_format",
    "output",
}
_REQUIRED_PLACEHOLDERS = {"portrait", "voice", "output"}
_ENGINE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_SUPPORTED_FORMATS = {"vertical", "landscape", "square"}
_APPROVED_LICENSE_STATUS = "approved_for_intended_use"


@dataclass(frozen=True)
class EngineSpec:
    """Immutable, validated description of one renderer implementation."""

    engine_id: str
    engine_version: str
    license_status: str
    license_reference: str
    commercial_use_verified: bool
    command: tuple[str, ...]
    required_assets: frozenset[str]
    supported_formats: frozenset[str]
    timeout_seconds: int

    def build_command(self, values: Mapping[str, str]) -> list[str]:
        """Render the argument vector without invoking a shell."""
        output_format = values.get("output_format", "")
        if output_format not in self.supported_formats:
            raise ValueError(f"Engine {self.engine_id} does not support format: {output_format}")
        missing_assets = sorted(asset for asset in self.required_assets if not values.get(asset))
        if missing_assets:
            raise ValueError(f"Engine {self.engine_id} is missing required assets: {', '.join(missing_assets)}")
        return [part.format_map(dict(values)) for part in self.command]


def _placeholders(command: tuple[str, ...]) -> set[str]:
    fields: set[str] = set()
    formatter = Formatter()
    for part in command:
        for _, field_name, _, _ in formatter.parse(part):
            if field_name:
                fields.add(field_name)
    return fields


def _validate(raw: dict) -> EngineSpec:
    if raw.get("schema_version") != 1:
        raise ValueError("Engine spec schema_version must be 1")

    engine_id = str(raw.get("engine_id", "")).strip()
    if not _ENGINE_ID.fullmatch(engine_id):
        raise ValueError("engine_id must be 2-64 lowercase letters, numbers, dot, dash, or underscore")

    engine_version = str(raw.get("engine_version", "")).strip()
    if not engine_version or len(engine_version) > 80:
        raise ValueError("engine_version is required and must be at most 80 characters")

    license_status = str(raw.get("license_status", "")).strip()
    license_reference = str(raw.get("license_reference", "")).strip()
    commercial_use_verified = raw.get("commercial_use_verified") is True
    allow_unapproved = os.getenv("VIDEO_CLONE_ALLOW_UNAPPROVED_ENGINE", "false").lower() == "true"
    if not allow_unapproved:
        if license_status != _APPROVED_LICENSE_STATUS or not commercial_use_verified:
            raise ValueError("Engine is not approved for the intended commercial use")
    if not license_reference or len(license_reference) > 500:
        raise ValueError("license_reference is required and must be at most 500 characters")

    command_raw = raw.get("command")
    if not isinstance(command_raw, list) or not command_raw or not all(isinstance(item, str) and item for item in command_raw):
        raise ValueError("command must be a non-empty JSON array of non-empty strings")
    command = tuple(command_raw)
    placeholders = _placeholders(command)
    unknown = sorted(placeholders - _ALLOWED_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Unknown engine command placeholders: {', '.join(unknown)}")
    missing = sorted(_REQUIRED_PLACEHOLDERS - placeholders)
    if missing:
        raise ValueError(f"Engine command is missing placeholders: {', '.join(missing)}")

    required_assets_raw = raw.get("required_assets", ["portrait", "voice"])
    if not isinstance(required_assets_raw, list):
        raise ValueError("required_assets must be an array")
    required_assets = frozenset(str(item) for item in required_assets_raw)
    if not {"portrait", "voice"}.issubset(required_assets):
        raise ValueError("required_assets must include portrait and voice")
    if not required_assets.issubset({"portrait", "voice", "source_video"}):
        raise ValueError("required_assets contains an unsupported asset kind")

    formats_raw = raw.get("supported_formats", sorted(_SUPPORTED_FORMATS))
    if not isinstance(formats_raw, list) or not formats_raw:
        raise ValueError("supported_formats must be a non-empty array")
    supported_formats = frozenset(str(item) for item in formats_raw)
    if not supported_formats.issubset(_SUPPORTED_FORMATS):
        raise ValueError("supported_formats contains an unsupported output format")

    timeout_seconds = int(raw.get("timeout_seconds", 7200))
    if not 60 <= timeout_seconds <= 14_400:
        raise ValueError("timeout_seconds must be between 60 and 14400")

    return EngineSpec(
        engine_id=engine_id,
        engine_version=engine_version,
        license_status=license_status,
        license_reference=license_reference,
        commercial_use_verified=commercial_use_verified,
        command=command,
        required_assets=required_assets,
        supported_formats=supported_formats,
        timeout_seconds=timeout_seconds,
    )


def load_engine_spec() -> EngineSpec:
    """Load one governed engine spec; legacy command mode is test-only and opt-in."""
    spec_path = os.getenv("VIDEO_CLONE_ENGINE_SPEC", "").strip()
    if spec_path:
        path = Path(spec_path).resolve()
        if not path.is_file():
            raise ValueError(f"Engine spec file does not exist: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Engine spec root must be a JSON object")
        return _validate(raw)

    legacy = os.getenv("VIDEO_CLONE_COMMAND", "").strip()
    legacy_allowed = os.getenv("VIDEO_CLONE_ALLOW_LEGACY_COMMAND", "false").lower() == "true"
    if not legacy or not legacy_allowed:
        raise ValueError("Set VIDEO_CLONE_ENGINE_SPEC to a governed engine spec")
    return _validate(
        {
            "schema_version": 1,
            "engine_id": "legacy-command-adapter",
            "engine_version": "1",
            "license_status": _APPROVED_LICENSE_STATUS,
            "license_reference": "explicit test-only compatibility adapter",
            "commercial_use_verified": True,
            "command": shlex.split(legacy),
            "required_assets": ["portrait", "voice"],
            "supported_formats": sorted(_SUPPORTED_FORMATS),
            "timeout_seconds": int(os.getenv("VIDEO_CLONE_TIMEOUT_SECONDS", "7200")),
        }
    )
