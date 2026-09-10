"""Local model adapter (Ollama).

Bound to loopback by configuration. Availability is probed, never assumed:
if Ollama is not reachable the adapter reports unavailable so the router can
make an explicit decision rather than hanging on a dead socket.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ModelAdapter, ModelRequest, ModelResponse, ModelTier, ModelUnavailable


class OllamaAdapter(ModelAdapter):
    provider = "ollama"

    def __init__(self, base_url: str, model: str, tier: ModelTier = ModelTier.LOCAL_LIGHT,
                 timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self.tier = tier
        self.timeout = timeout

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def generate(self, request: ModelRequest) -> ModelResponse:
        body = json.dumps({
            "model": self.model,
            "prompt": request.prompt,
            "system": request.system,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"ollama request failed: {exc}") from exc

        text = str(payload.get("response", ""))
        if not text:
            raise ModelUnavailable("ollama returned an empty response")
        return ModelResponse(
            text=text, model=self.model, tier=self.tier, provider=self.provider,
            trace_id=request.trace_id,
            usage={
                "prompt_eval_count": payload.get("prompt_eval_count", 0),
                "eval_count": payload.get("eval_count", 0),
            },
        )
