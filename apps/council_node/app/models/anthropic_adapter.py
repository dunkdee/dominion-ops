"""External adapter — Anthropic. Optional by design.

Same contract as the OpenAI adapter: opt-in, fail-closed when unconfigured,
and it never lets a transport exception carry request content into a log.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ModelAdapter, ModelRequest, ModelResponse, ModelTier, ModelUnavailable

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicAdapter(ModelAdapter):
    provider = "anthropic"
    tier = ModelTier.EXTERNAL

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", enabled: bool = False,
                 timeout: int = 120) -> None:
        self._api_key = api_key or ""
        self.model = model
        self.name = f"anthropic:{model}"
        self._enabled = bool(enabled)
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self._enabled and self._api_key)

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.available():
            raise ModelUnavailable(
                "anthropic adapter is disabled or unconfigured; external models are opt-in"
            )
        body = json.dumps({
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system or None,
            "messages": [{"role": "user", "content": request.prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": API_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"anthropic request failed: {type(exc).__name__}") from None

        blocks = payload.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise ModelUnavailable("anthropic returned an unexpected response shape")
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        if not text:
            raise ModelUnavailable("anthropic returned no text content")
        return ModelResponse(
            text=text, model=self.model, tier=self.tier, provider=self.provider,
            trace_id=request.trace_id, usage=payload.get("usage", {}) or {},
        )
