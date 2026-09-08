from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from model_gateway import route_model


@dataclass(frozen=True)
class IntelligenceConfig:
    primary_url: str
    primary_model: str
    primary_api_key: str
    buddy_fallback_url: str
    buddy_fallback_token_file: str
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "IntelligenceConfig":
        return cls(
            primary_url=os.getenv("NEMOTRON_BASE_URL", "").rstrip("/"),
            primary_model=os.getenv("NEMOTRON_MODEL", "nemotron-3"),
            primary_api_key=os.getenv("NEMOTRON_API_KEY", ""),
            buddy_fallback_url=os.getenv("BUDDY_FALLBACK_URL", "http://127.0.0.1:5070").rstrip("/"),
            buddy_fallback_token_file=os.getenv(
                "BUDDY_FALLBACK_TOKEN_FILE", "/run/secrets/buddy_web_token"
            ),
            timeout_seconds=int(os.getenv("INTELLIGENCE_TIMEOUT_SECONDS", "60")),
        )


SYSTEM_PROMPT = """You are Buddy: the Founder's personal AI operator and Dominion Intelligence lead inside RADAH MEMSHALAH.
You are not a generic assistant or a disposable chatbot. Maintain continuity with the Founder's operating context, priorities, decisions, working style, and authorized memory when those sources are available.
Founder authority is final. Your job is to help build and operate an elite, truthful, scalable, owned AI business ecosystem.
Prioritize cash flow, quality, measurable outcomes, repeatable systems, documentation, and closed loops.
Use Dominion memory and tools when available. Never fabricate completion, revenue, deployment status, or evidence.
Do not pretend to remember information that is not actually available from memory, runtime context, or tools.
For every operational answer, identify the objective, the next concrete action, the verification gate, and what should be recorded in memory.

Voice and conversational register:
- Speak naturally in a confident Black American conversational register, with contemporary slang and AAVE-influenced phrasing when it fits the moment.
- Keep it organic and restrained. Never force slang into every sentence, imitate a caricature, or rely on racial stereotypes.
- Match the Founder's cadence when useful while preserving accuracy and command clarity.
- Keep production status, money, risk, code, and governance statements precise even when the surrounding delivery is casual.
- Sound like a trusted personal operator who knows the system, not a corporate help-desk bot.
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


def _read_secret(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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


def call_buddy_operator(message: str, context: str = "") -> dict[str, Any] | None:
    """Use the canonical authenticated Buddy operator as the reasoning fallback.

    Conductor on port 5060 is an orchestration service and does not expose a
    supported chat contract. Buddy Web on port 5070 owns the canonical
    /buddy/api/chat contract and calls get_operator().handle() behind the
    existing Buddy bearer-token boundary.
    """
    cfg = IntelligenceConfig.from_env()
    token = _read_secret(cfg.buddy_fallback_token_file)
    if not cfg.buddy_fallback_url or not token:
        return None

    payload = {
        "message": message,
        "session_id": "dominion-command-center",
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        parsed = _post_json(
            f"{cfg.buddy_fallback_url}/buddy/api/chat",
            payload,
            headers,
            cfg.timeout_seconds,
        )
        status = str(parsed.get("status") or "").upper()
        answer = str(parsed.get("response") or "").strip()
        if answer and status not in {"BLOCKED", "ERROR"}:
            return {"answer": answer, "source": "buddy_operator", "raw": parsed}
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None
    return None


def route_intelligence(message: str, context: str = "", task: str = "general") -> dict[str, Any] | None:
    governed = route_model(message, context, SYSTEM_PROMPT, task=task)
    if governed:
        return governed
    primary = call_nemotron(message, context)
    if primary:
        return primary
    return call_buddy_operator(message, context)
