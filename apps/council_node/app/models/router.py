"""Model router — tier escalation with a hard redaction boundary.

Two responsibilities, and the second is the important one:

  route     pick the cheapest tier that can serve the task, escalating only
            when the task genuinely needs it and policy allows it
  redact    every outbound prompt passes through the same redactor the logs
            use, and a prompt that still looks like it carries a secret after
            redaction is refused outright rather than sent

The refusal is the point. Redaction can fail -- a novel key format, a secret
we never held in config. So after redacting, the router re-scans, and if a
recognisable secret shape survives it raises SecretInPromptError instead of
shipping it to a third party. Failing a task is recoverable; leaking a
credential to an external provider is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..logging import get_logger, redact
from .base import ModelAdapter, ModelRequest, ModelResponse, ModelTier, ModelUnavailable

log = get_logger("models.router")

# Data classifications that may never leave the machine.
NO_EXTERNAL_CLASSIFICATIONS = frozenset({"sensitive", "secret", "restricted"})

# Shapes that must never survive into an outbound prompt.
_RESIDUAL_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s@]+@"),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class SecretInPromptError(RuntimeError):
    """A prompt still carried a secret after redaction. The call was refused."""


@dataclass(frozen=True)
class RoutingResult:
    response: ModelResponse
    tier_used: ModelTier
    escalated: bool
    redacted: bool


def scan_for_secrets(text: str) -> tuple[str, ...]:
    """Return the names of secret shapes found. Empty means clean."""
    found: list[str] = []
    for pattern in _RESIDUAL_SECRET_PATTERNS:
        if pattern.search(text):
            found.append(pattern.pattern[:32])
    return tuple(found)


class ModelRouter:
    def __init__(
        self,
        adapters: list[ModelAdapter],
        *,
        secret_values: tuple[str, ...] = (),
        allow_external: bool = False,
    ) -> None:
        self.adapters = sorted(adapters, key=lambda a: int(a.tier))
        self._secrets = secret_values
        self.allow_external = allow_external

    def available_models(self) -> list[dict]:
        return [
            {
                "name": a.name, "provider": a.provider,
                "tier": int(a.tier), "available": a.available(),
            }
            for a in self.adapters
        ]

    def _sanitize(self, request: ModelRequest, external: bool) -> ModelRequest:
        """Redact, then verify. Refuses rather than sends a surviving secret."""
        prompt = redact(request.prompt, self._secrets)
        system = redact(request.system, self._secrets)

        if external:
            residual = scan_for_secrets(prompt) + scan_for_secrets(system)
            if residual:
                raise SecretInPromptError(
                    f"refusing external model call: {len(residual)} secret-shaped value(s) "
                    "survived redaction"
                )
        return ModelRequest(
            prompt=prompt, system=system, max_tokens=request.max_tokens,
            temperature=request.temperature, trace_id=request.trace_id,
            data_classification=request.data_classification,
        )

    def route(self, request: ModelRequest, *, minimum_tier: ModelTier = ModelTier.LOCAL_LIGHT,
              maximum_tier: ModelTier | None = None) -> RoutingResult:
        max_tier = maximum_tier if maximum_tier is not None else ModelTier.EXTERNAL

        # Sensitive data never escalates off the machine, whatever the caller asked.
        if request.data_classification in NO_EXTERNAL_CLASSIFICATIONS:
            max_tier = min(max_tier, ModelTier.LOCAL_STRONG)
        if not self.allow_external:
            max_tier = min(max_tier, ModelTier.LOCAL_STRONG)

        errors: list[str] = []
        for adapter in self.adapters:
            if adapter.tier < minimum_tier or adapter.tier > max_tier:
                continue
            if not adapter.available():
                errors.append(f"{adapter.name}: unavailable")
                continue

            external = adapter.tier is ModelTier.EXTERNAL
            sanitized = self._sanitize(request, external)
            try:
                response = adapter.generate(sanitized)
            except ModelUnavailable as exc:
                errors.append(f"{adapter.name}: {exc}")
                continue

            return RoutingResult(
                response=response,
                tier_used=adapter.tier,
                escalated=adapter.tier > minimum_tier,
                redacted=sanitized.prompt != request.prompt or sanitized.system != request.system,
            )

        # No adapter served the request. This is a failure, not an empty answer.
        raise ModelUnavailable(
            "no model adapter could serve the request: " + ("; ".join(errors) or "none eligible")
        )
