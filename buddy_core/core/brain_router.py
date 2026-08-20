"""Multi-model skill router for Buddy.

Buddy owns the mission. Providers are interchangeable specialist brains. The
router chooses one best-fit available provider and falls back on failure. It
does not automatically call multiple paid providers, which could create
unbounded spend without a standing Founder policy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from core import brain


@dataclass
class BrainResult:
    text: str
    provider: str
    model: str
    task_type: str
    fallback_hops: int = 0

    def to_dict(self):
        return asdict(self)


_MODELS = {
    "claude": "claude-sonnet-4-6",
    "groq": getattr(brain, "GROQ_MODEL", "llama-3.3-70b-versatile"),
    "gemini_pro": "gemini-2.5-pro",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "ollama": getattr(brain, "OLLAMA_MODEL", "OLLAMA_MODEL"),
}


def _available(mode: str) -> bool:
    checks = {
        "claude": brain.has_claude,
        "groq": brain.has_groq,
        "gemini": brain.has_gemini,
        "gemini_pro": brain.has_gemini,
        "openai": brain.has_openai,
        "ollama": brain.is_ollama_running,
    }
    fn = checks.get(mode)
    return bool(fn and fn())


def _call(mode: str, prompt: str, system: str | None = None) -> str:
    system = system or brain.BUDDY_SYSTEM
    if mode == "claude":
        return brain.ask_claude(prompt, system)
    if mode == "groq":
        return brain.ask_groq(prompt, system)
    if mode == "gemini_pro":
        return brain.ask_gemini_pro(prompt, system)
    if mode == "gemini":
        return brain.ask_gemini(prompt, system)
    if mode == "openai":
        return brain.ask_openai(prompt, system)
    if mode == "ollama":
        return brain.ask_ollama(f"SYSTEM:\n{system}\n\nUSER:\n{prompt}")
    raise ValueError(f"unknown brain mode: {mode}")


def route_order(task_type: str, prompt: str = "") -> list[str]:
    task = (task_type or "general").lower()
    text = prompt.lower()
    if task in {"coding", "architecture", "debugging", "complex_planning", "legal_analysis"}:
        return ["claude", "gemini_pro", "groq", "ollama"]
    if task in {"research_synthesis", "deep_synthesis", "large_context"}:
        return ["gemini_pro", "claude", "groq", "ollama"]
    if task in {"creative", "drafting", "classification", "summarization", "general"}:
        if any(w in text for w in ("refactor", "architecture", "multi-step", "contract", "debug")):
            return ["claude", "groq", "gemini_pro", "ollama"]
        return ["groq", "gemini", "claude", "ollama"]
    return ["groq", "claude", "gemini", "ollama"]


def ask_best(prompt: str, *, task_type: str = "general", system: str | None = None,
             max_fallback_hops: int = 3) -> BrainResult:
    errors = []
    for hop, mode in enumerate(route_order(task_type, prompt)):
        if hop > max_fallback_hops:
            break
        if not _available(mode):
            errors.append(f"{mode}:unavailable")
            continue
        try:
            text = _call(mode, prompt, system)
            if text and text.strip():
                provider = {
                    "claude": "anthropic", "groq": "groq", "gemini": "google",
                    "gemini_pro": "google", "openai": "openai", "ollama": "local",
                }[mode]
                return BrainResult(text=text.strip(), provider=provider,
                                   model=_MODELS[mode], task_type=task_type,
                                   fallback_hops=hop)
            errors.append(f"{mode}:empty")
        except Exception as exc:
            errors.append(f"{mode}:{type(exc).__name__}")
    raise RuntimeError("all governed brains unavailable: " + ",".join(errors))
