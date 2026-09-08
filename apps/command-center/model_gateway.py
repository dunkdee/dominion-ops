from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


SUPPORTED_PROVIDERS = {"openai_compatible", "anthropic"}
DEFAULT_ROUTES_FILE = "/etc/dominion/model-routes.json"


@dataclass(frozen=True)
class ModelRoute:
    name: str
    provider: str
    base_url: str
    model: str
    enabled: bool
    priority: int
    tasks: tuple[str, ...]
    timeout_seconds: int
    api_key_file: str = ""
    api_key_env: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ModelRoute":
        provider = str(value.get("provider") or "").strip()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported-provider:{provider}")
        tasks = value.get("tasks") or ["general"]
        if not isinstance(tasks, list) or not all(isinstance(item, str) for item in tasks):
            raise ValueError("tasks-must-be-a-string-list")
        return cls(
            name=str(value.get("name") or "").strip(),
            provider=provider,
            base_url=str(value.get("base_url") or "").rstrip("/"),
            model=str(value.get("model") or "").strip(),
            enabled=bool(value.get("enabled", False)),
            priority=int(value.get("priority", 100)),
            tasks=tuple(item.strip() for item in tasks if item.strip()),
            timeout_seconds=max(1, int(value.get("timeout_seconds", 60))),
            api_key_file=str(value.get("api_key_file") or "").strip(),
            api_key_env=str(value.get("api_key_env") or "").strip(),
        )

    def usable_for(self, task: str) -> bool:
        if not self.enabled or not self.name or not self.base_url or not self.model:
            return False
        return "*" in self.tasks or task in self.tasks or "general" in self.tasks


def _read_secret_file(path: str) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resolve_api_key(route: ModelRoute) -> str:
    # Secret files are preferred so credentials do not need to be embedded in
    # configuration, logs, process arguments, repository files, or screenshots.
    secret = _read_secret_file(route.api_key_file)
    if secret:
        return secret
    if route.api_key_env:
        return os.getenv(route.api_key_env, "").strip()
    return ""


def load_routes(path: str | None = None) -> list[ModelRoute]:
    routes_path = Path(path or os.getenv("DOMINION_MODEL_ROUTES_FILE", DEFAULT_ROUTES_FILE))
    if not routes_path.exists():
        return []
    try:
        payload = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_routes = payload.get("routes", []) if isinstance(payload, dict) else []
    if not isinstance(raw_routes, list):
        return []

    routes: list[ModelRoute] = []
    for raw in raw_routes:
        if not isinstance(raw, dict):
            continue
        try:
            route = ModelRoute.from_mapping(raw)
        except (TypeError, ValueError):
            continue
        if route.usable_for("general") or route.tasks:
            routes.append(route)
    return sorted(routes, key=lambda item: (item.priority, item.name))


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
            raise ValueError("provider-returned-non-object")
        return parsed


def _call_openai_compatible(route: ModelRoute, api_key: str, message: str, context: str, system_prompt: str) -> str:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": route.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"Dominion context:\n{context}" if context else "Dominion context: not supplied."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.35,
        "stream": False,
    }
    parsed = _post_json(f"{route.base_url}/v1/chat/completions", payload, headers, route.timeout_seconds)
    choices = parsed.get("choices") or []
    if choices and isinstance(choices[0], dict):
        content = ((choices[0].get("message") or {}).get("content"))
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _call_anthropic(route: ModelRoute, api_key: str, message: str, context: str, system_prompt: str) -> str:
    if not api_key:
        return ""
    system = system_prompt
    if context:
        system += f"\n\nDominion context:\n{context}"
    payload = {
        "model": route.model,
        "max_tokens": 4096,
        "temperature": 0.35,
        "system": system,
        "messages": [{"role": "user", "content": message}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    parsed = _post_json(f"{route.base_url}/v1/messages", payload, headers, route.timeout_seconds)
    blocks = parsed.get("content") or []
    if isinstance(blocks, list):
        text = "\n".join(
            str(block.get("text") or "").strip()
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        return text
    return ""


def route_model(
    message: str,
    context: str,
    system_prompt: str,
    task: str = "general",
    routes_file: str | None = None,
) -> dict[str, Any] | None:
    """Route one reasoning request through the approved model list.

    The function fails closed: disabled, malformed, unavailable, or unauthenticated
    routes are skipped. It never discovers arbitrary providers and never emits a
    credential. Provider failures fall through to the next approved route.
    """
    task = (task or "general").strip().lower()
    for route in load_routes(routes_file):
        if not route.usable_for(task):
            continue
        api_key = _resolve_api_key(route)
        # External Anthropic always requires a key. OpenAI-compatible local
        # endpoints may intentionally be unauthenticated on loopback/private
        # networks, so absence of a key is permitted for that provider kind.
        if route.provider == "anthropic" and not api_key:
            continue
        try:
            if route.provider == "openai_compatible":
                answer = _call_openai_compatible(route, api_key, message, context, system_prompt)
            else:
                answer = _call_anthropic(route, api_key, message, context, system_prompt)
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            continue
        if answer:
            return {
                "answer": answer,
                "source": "model_gateway",
                "route": route.name,
                "provider": route.provider,
                "model": route.model,
            }
    return None
