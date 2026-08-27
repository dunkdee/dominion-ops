from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class IntelligenceConfig:
    primary_url: str
    primary_model: str
    primary_api_key: str
    conductor_url: str
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "IntelligenceConfig":
        return cls(
            primary_url=os.getenv("NEMOTRON_BASE_URL", "").rstrip("/"),
            primary_model=os.getenv("NEMOTRON_MODEL", "nemotron-3"),
            primary_api_key=os.getenv("NEMOTRON_API_KEY", ""),
            conductor_url=os.getenv("CONDUCTOR_URL", "http://host.docker.internal:5060").rstrip("/"),
            timeout_seconds=int(os.getenv("INTELLIGENCE_TIMEOUT_SECONDS", "60")),
        )


SYSTEM_PROMPT = """You are Buddy, Dominion Intelligence: the lead reasoning and operating brain for Dominion.
Founder authority is final. Your job is to help build an elite, truthful, scalable, owned AI business ecosystem.
Prioritize cash flow, quality, measurable outcomes, repeatable systems, documentation, and closed loops.
Use Dominion memory and tools when available. Never fabricate completion, revenue, deployment status, or evidence.
For every operational answer, identify the objective, the next concrete action, the verification gate, and what should be recorded in memory.

Voice and conversational register:
- Speak naturally in a confident Black American conversational register, with contemporary slang and AAVE-influenced phrasing when it fits the moment.
- Keep it organic and restrained. Never force slang into every sentence, imitate a caricature, or rely on racial stereotypes.
- Match the Founder's cadence when useful while preserving accuracy and command clarity.
- Keep production status, money, risk, code, and governance statements precise even when the surrounding delivery is casual.
- Sound like a capable operator who knows the system, not a corporate help-desk bot.
"""


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("Provider returned a non-object response")
        return parsed


def call_nemotron(message: str, context: str = "") -> dict[str, Any] | None:
    cfg = IntelligenceConfig.from_env()
    if not cfg.primary_url:
        return None

    headers: dict[str, str] = {}
    if cfg.primary_api_key:
        headers["Authorization"] = f"Bearer {cfg.primary_api_key}"

    payload = {
        "model": cfg.primary_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Dominion context:\n{context}" if context else "Dominion context: not supplied."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.35,
        "stream": False,
    }

    try:
        result = _post_json(
            f"{cfg.primary_url}/v1/chat/completions",
            payload,
            headers,
            cfg.timeout_seconds,
        )
        choices = result.get("choices") or []
        if choices and isinstance(choices[0], dict):
            content = ((choices[0].get("message") or {}).get("content"))
            if content:
                return {"answer": content, "source": "nemotron", "raw": result}
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None
    return None


def call_conductor(message: str, context: str = "") -> dict[str, Any] | None:
    cfg = IntelligenceConfig.from_env()
    governed_message = "\n\n".join(
        part
        for part in (
            SYSTEM_PROMPT,
            f"Dominion context:\n{context}" if context else "Dominion context: not supplied.",
            f"Founder command:\n{message}",
        )
        if part
    )
    payload = {
        "message": governed_message,
        "source": "dominion-command-center",
        "persona": "buddy",
    }
    for endpoint in ("/chat", "/api/chat", "/invoke"):
        try:
            parsed = _post_json(f"{cfg.conductor_url}{endpoint}", payload, {}, cfg.timeout_seconds)
            answer = parsed.get("response") or parsed.get("answer") or parsed.get("message")
            if answer:
                return {"answer": answer, "source": "conductor", "raw": parsed}
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
    return None


def route_intelligence(message: str, context: str = "") -> dict[str, Any] | None:
    primary = call_nemotron(message, context)
    if primary:
        return primary
    return call_conductor(message, context)
