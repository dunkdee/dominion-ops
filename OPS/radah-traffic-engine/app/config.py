from __future__ import annotations
import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "radah-traffic-engine")
    environment: str = os.getenv("ENVIRONMENT", "production")
    db_path: str = os.getenv("DB_PATH", "/data/traffic_engine.db")
    api_key: str = os.getenv("API_KEY", "")
    radah_shared_secret: str = os.getenv("RADAH_SHARED_SECRET", "")
    require_radah_signature: bool = _bool("REQUIRE_RADAH_SIGNATURE", True)
    max_body_bytes: int = int(os.getenv("MAX_BODY_BYTES", "65536"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
    audit_hmac_key: str = os.getenv("AUDIT_HMAC_KEY", "")
    allow_docs: bool = _bool("ALLOW_DOCS", False)
    enable_public_lead_capture: bool = _bool("ENABLE_PUBLIC_LEAD_CAPTURE", False)
    privacy_policy_url: str = os.getenv("PRIVACY_POLICY_URL", "")
    lead_retention_days: int = int(os.getenv("LEAD_RETENTION_DAYS", "90"))

    def validate(self) -> None:
        problems = []
        if self.environment == "production":
            if len(self.api_key) < 24:
                problems.append("API_KEY must be set to a strong value (>=24 chars) in production.")
            if self.require_radah_signature and len(self.radah_shared_secret) < 24:
                problems.append("RADAH_SHARED_SECRET must be set (>=24 chars) when signatures are required.")
            if len(self.audit_hmac_key) < 24:
                problems.append("AUDIT_HMAC_KEY must be set to a strong value (>=24 chars) in production.")
        if self.max_body_bytes < 1024:
            problems.append("MAX_BODY_BYTES is too small.")
        if not (1 <= self.rate_limit_per_minute <= 10000):
            problems.append("RATE_LIMIT_PER_MINUTE must be between 1 and 10000.")
        if not (1 <= self.lead_retention_days <= 365):
            problems.append("LEAD_RETENTION_DAYS must be between 1 and 365.")
        if self.enable_public_lead_capture:
            if not self.privacy_policy_url.startswith("https://") or "example.com" in self.privacy_policy_url.lower():
                problems.append("PRIVACY_POLICY_URL must be a real https URL (not example.com) when public lead capture is enabled.")
        if problems:
            raise RuntimeError("Invalid configuration: " + " ".join(problems))


settings = Settings()
settings.validate()
