"""Council Node configuration.

Every value is read from the environment. Nothing here holds a default that
would silently point production at a developer's machine, and nothing here
prints a secret: `Settings.redacted()` is the only rendering, and it names
which secrets are present without revealing any value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_PREFIX = "COUNCIL_"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"{ENV_PREFIX}{name}", default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = _env(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# Secrets are recognised by name so logging, receipts and outbound model
# prompts can all share one definition of "must never be shown".
SECRET_ENV_SUFFIXES = (
    "PASSWORD", "SECRET", "TOKEN", "API_KEY", "KEY", "DSN", "CREDENTIAL",
)


@dataclass(frozen=True)
class Settings:
    # Service
    bind_host: str = field(default_factory=lambda: _env("BIND_HOST", "127.0.0.1"))
    bind_port: int = field(default_factory=lambda: _int("BIND_PORT", 8200))
    environment: str = field(default_factory=lambda: _env("ENVIRONMENT", "development"))

    # Data plane
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL"))
    receipt_dir: Path = field(
        default_factory=lambda: Path(
            _env("RECEIPT_DIR", "/var/lib/dominion/receipts")
        ).expanduser()
    )

    # Governance
    governance_dir: Path = field(
        default_factory=lambda: Path(_env("GOVERNANCE_DIR", "governance")).expanduser()
    )

    # Models
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    local_model: str = field(default_factory=lambda: _env("LOCAL_MODEL", "qwen2.5:7b"))
    embedding_model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "nomic-embed-text"))
    # External adapters are opt-in. Absent config means the adapter reports
    # itself unavailable rather than half-working.
    external_models_enabled: bool = field(default_factory=lambda: _flag("EXTERNAL_MODELS_ENABLED", False))
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))

    # Founder control
    founder_token: str = field(default_factory=lambda: _env("FOUNDER_TOKEN"))

    # Scheduler
    sweep_interval_hours: int = field(default_factory=lambda: _int("SWEEP_INTERVAL_HOURS", 3))
    lane_stale_hours: int = field(default_factory=lambda: _int("LANE_STALE_HOURS", 6))

    def secret_values(self) -> tuple[str, ...]:
        """Every secret this process holds, for the log/prompt redactor."""
        candidates = (
            self.founder_token,
            self.openai_api_key,
            self.anthropic_api_key,
            self.database_url,
            self.redis_url,
        )
        # Short strings would over-redact ordinary text.
        return tuple(v for v in candidates if v and len(v) >= 8)

    def redacted(self) -> dict:
        """Safe to log, safe to return from /api/status."""
        return {
            "environment": self.environment,
            "bind": f"{self.bind_host}:{self.bind_port}",
            "database_configured": bool(self.database_url),
            "redis_configured": bool(self.redis_url),
            "receipt_dir": str(self.receipt_dir),
            "ollama_url": self.ollama_url,
            "local_model": self.local_model,
            "external_models_enabled": self.external_models_enabled,
            "openai_configured": bool(self.openai_api_key),
            "anthropic_configured": bool(self.anthropic_api_key),
            "founder_gate_configured": bool(self.founder_token),
            "sweep_interval_hours": self.sweep_interval_hours,
        }


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_tests() -> None:
    global _settings
    _settings = None
