"""Model routing and the outbound redaction boundary (Gate 5, Gate 8).

The critical assertion here is the refusal: when a secret survives redaction,
the router must raise rather than send. Failing a task is recoverable;
handing a live credential to a third-party API is not.
"""

from __future__ import annotations

import pytest

from apps.council_node.app.models.base import (
    ModelAdapter, ModelRequest, ModelResponse, ModelTier, ModelUnavailable,
)
from apps.council_node.app.models.anthropic_adapter import AnthropicAdapter
from apps.council_node.app.models.openai_adapter import OpenAIAdapter
from apps.council_node.app.models.router import (
    ModelRouter, SecretInPromptError, scan_for_secrets,
)

OPENAI_KEY = "sk-proj-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"


class FakeAdapter(ModelAdapter):
    """Records what it was actually asked to send."""

    def __init__(self, name: str, tier: ModelTier, available: bool = True) -> None:
        self.name = name
        self.provider = name
        self.tier = tier
        self._available = available
        self.seen: list[ModelRequest] = []

    def available(self) -> bool:
        return self._available

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.seen.append(request)
        return ModelResponse(
            text="ok", model=self.name, tier=self.tier,
            provider=self.provider, trace_id=request.trace_id,
        )


def test_prefers_the_lowest_eligible_tier():
    light = FakeAdapter("light", ModelTier.LOCAL_LIGHT)
    strong = FakeAdapter("strong", ModelTier.LOCAL_STRONG)
    router = ModelRouter([strong, light])
    result = router.route(ModelRequest(prompt="hello"))
    assert result.tier_used is ModelTier.LOCAL_LIGHT
    assert not strong.seen


def test_escalates_when_the_lower_tier_is_unavailable():
    light = FakeAdapter("light", ModelTier.LOCAL_LIGHT, available=False)
    strong = FakeAdapter("strong", ModelTier.LOCAL_STRONG)
    result = ModelRouter([light, strong]).route(ModelRequest(prompt="hi"))
    assert result.tier_used is ModelTier.LOCAL_STRONG
    assert result.escalated is True


def test_external_tier_is_unreachable_unless_allowed():
    local = FakeAdapter("local", ModelTier.LOCAL_LIGHT, available=False)
    external = FakeAdapter("external", ModelTier.EXTERNAL)
    router = ModelRouter([local, external], allow_external=False)
    with pytest.raises(ModelUnavailable):
        router.route(ModelRequest(prompt="hi"))
    assert not external.seen, "external adapter must not be called when disabled"


def test_external_tier_is_used_when_explicitly_allowed():
    local = FakeAdapter("local", ModelTier.LOCAL_LIGHT, available=False)
    external = FakeAdapter("external", ModelTier.EXTERNAL)
    router = ModelRouter([local, external], allow_external=True)
    assert router.route(ModelRequest(prompt="hi")).tier_used is ModelTier.EXTERNAL


def test_sensitive_data_never_escalates_off_the_machine():
    local = FakeAdapter("local", ModelTier.LOCAL_LIGHT, available=False)
    external = FakeAdapter("external", ModelTier.EXTERNAL)
    router = ModelRouter([local, external], allow_external=True)
    with pytest.raises(ModelUnavailable):
        router.route(ModelRequest(prompt="patient record", data_classification="sensitive"))
    assert not external.seen


def test_configured_secret_is_redacted_before_sending():
    secret = "founder-token-abcdefghijklmnop"
    external = FakeAdapter("external", ModelTier.EXTERNAL)
    router = ModelRouter([external], secret_values=(secret,), allow_external=True)
    result = router.route(ModelRequest(prompt=f"the token is {secret}"))
    assert secret not in external.seen[0].prompt
    assert result.redacted is True


def test_unknown_secret_shape_refuses_the_external_call(monkeypatch):
    """A secret we never held must stop the call, not ride along.

    Redaction is neutered here to simulate a key format the redactor does not
    yet know. The router's post-redaction scan is the last line of defence and
    must fire.
    """
    import apps.council_node.app.models.router as router_module

    monkeypatch.setattr(router_module, "redact", lambda text, secrets=(): text)
    external = FakeAdapter("external", ModelTier.EXTERNAL)
    router = ModelRouter([external], allow_external=True)

    with pytest.raises(SecretInPromptError, match="survived redaction"):
        router.route(ModelRequest(prompt=f"use {OPENAI_KEY} please"))
    assert not external.seen, "nothing may be sent once a secret is detected"


def test_local_tier_is_not_blocked_by_the_external_scan(monkeypatch):
    """The refusal applies to outbound external calls, not local models."""
    import apps.council_node.app.models.router as router_module

    monkeypatch.setattr(router_module, "redact", lambda text, secrets=(): text)
    local = FakeAdapter("local", ModelTier.LOCAL_LIGHT)
    router = ModelRouter([local], allow_external=False)
    result = router.route(ModelRequest(prompt=f"use {OPENAI_KEY}"))
    assert result.tier_used is ModelTier.LOCAL_LIGHT


def test_scan_detects_known_shapes():
    assert scan_for_secrets(f"x {OPENAI_KEY} y")
    assert scan_for_secrets("postgres://u:p@host/db")
    assert not scan_for_secrets("an entirely ordinary sentence")


def test_no_adapter_available_raises_rather_than_returning_empty():
    dead = FakeAdapter("dead", ModelTier.LOCAL_LIGHT, available=False)
    with pytest.raises(ModelUnavailable, match="no model adapter"):
        ModelRouter([dead]).route(ModelRequest(prompt="hi"))


# ── external adapters are opt-in (Gate 5) ───────────────────────────────

def test_external_adapters_report_unavailable_without_configuration():
    assert OpenAIAdapter("", enabled=True).available() is False
    assert OpenAIAdapter("key-present", enabled=False).available() is False
    assert AnthropicAdapter("", enabled=True).available() is False
    assert AnthropicAdapter("key-present", enabled=False).available() is False


def test_disabled_external_adapter_raises_instead_of_calling_out():
    for adapter in (OpenAIAdapter("", enabled=False), AnthropicAdapter("", enabled=False)):
        with pytest.raises(ModelUnavailable, match="opt-in"):
            adapter.generate(ModelRequest(prompt="hi"))
