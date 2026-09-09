"""External adapter — OpenAI. Optional by design.

The work order is explicit that proprietary models are external services and
are never claimed to run locally. This adapter reports unavailable unless it
is both configured and explicitly enabled, so an absent key degrades to
"cannot serve" rather than to a confusing runtime error.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ModelAdapter, ModelRequest, ModelResponse, ModelTier, ModelUnavailable

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIAdapter(ModelAdapter):
    provider = "openai"
    tier = ModelTier.EXTERNAL

    def __init__(self, api_key: str, model: str = "gpt-4o", enabled: bool = False,
                 timeout: int = 120) -> None:
        self._api_key = api_key or ""
        self.model = model
        self.name = f"openai:{model}"
        self._enabled = bool(enabled)
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self._enabled and self._api_key)

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.available():
            raise ModelUnavailable(
                "openai adapter is disabled or unconfigured; external models are opt-in"
            )
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        body = json.dumps({
            "model": self.model, "messages": messages,
            "max_tokens": request.max_tokens, "temperature": request.temperature,
        }).encode("utf-8")
        req = urllib.request.Request(
            API_URL, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            # The exception text may echo the request; never propagate it raw.
            raise ModelUnavailable(f"openai request failed: {type(exc).__name__}") from None

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelUnavailable("openai returned an unexpected response shape") from exc
        return ModelResponse(
            text=str(text), model=self.model, tier=self.tier, provider=self.provider,
            trace_id=request.trace_id, usage=payload.get("usage", {}) or {},
        )
