"""Model adapter contract.

Tiers follow the work order: deterministic code first, then local models,
then external providers. A tier is a routing hint, not a guarantee -- the
router still decides, and policy can forbid a tier outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class ModelUnavailable(RuntimeError):
    """The adapter cannot serve this request. Never a silent fallback."""


class ModelTier(IntEnum):
    DETERMINISTIC = 0   # no model at all
    LOCAL_LIGHT = 1
    LOCAL_STRONG = 2
    EXTERNAL = 3


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    system: str = ""
    max_tokens: int = 1024
    temperature: float = 0.2
    trace_id: str = ""
    data_classification: str = "internal"   # public | internal | sensitive


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str
    tier: ModelTier
    provider: str
    trace_id: str = ""
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "tier": int(self.tier),
            "provider": self.provider,
            "trace_id": self.trace_id,
            "usage": self.usage,
        }


class ModelAdapter:
    """Base adapter. Subclasses must not swallow errors into empty output."""

    name: str = "base"
    provider: str = "none"
    tier: ModelTier = ModelTier.LOCAL_LIGHT

    def available(self) -> bool:
        raise NotImplementedError

    def generate(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError
