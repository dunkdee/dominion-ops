"""Multi-model skill router for Buddy.

Buddy owns the mission. Providers are interchangeable specialist brains. The
router chooses one best-fit available provider and falls back on failure. It
does not automatically call multiple paid providers, which could create
unbounded spend without a standing Founder policy.

Canonical governance is non-bypassable: every routed call receives Buddy's
base system prompt, constitution, and Founder operating context before any
narrower task-specific system rules.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

try:  # VM runtime commonly has buddy_core itself on sys.path.
    from core import brain
except ImportError:  # Repository/package execution used by CI/tests.
    from buddy_core.core import brain


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

_CONFIG = Path(__file__).resolve().parents[1] / "config"
_CONSTITUTION_FILE = _CONFIG / "BUDDY_CONSTITUTION.md"
_FOUNDER_CONTEXT_FILE = _CONFIG / "FOUNDER_OPERATING_CONTEXT.md"
_CANONICAL_FILE_LIMIT = 12000


def _read_context(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")[:_CANONICAL_FILE_LIMIT].strip()
    except OSError:
        return ""


def canonical_system_prompt() -> str:
    """Return the non-bypassable canonical Buddy governance/context prompt."""
    parts = [
        str(getattr(brain, "BUDDY_SYSTEM", "") or "").strip(),
        _read_context(_CONSTITUTION_FILE),
        _read_context(_FOUNDER_CONTEXT_FILE),
    ]
    return "\n\n".join(part for part in parts if part)


def _compose_system(system: str | None = None) -> str:
    """Compose narrower task rules under canonical governance, never instead of it."""
    canonical = canonical_system_prompt()
    custom = (system or "").strip()
    if not custom:
        return canonical
    if custom in canonical:
        return canonical
    return (
        canonical
        + "\n\nTASK-SPECIFIC SYSTEM RULES — subordinate to canonical governance:\n"
        + custom
    )


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
    system = _compose_system(system)
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
        return ["claude", "openai", "gemini_pro", "groq", "ollama"]
    if task in {"research_synthesis", "deep_synthesis", "large_context"}:
        return ["gemini_pro", "claude", "openai", "groq", "ollama"]
    if task in {"creative", "drafting", "classification", "summarization", "general"}:
        if any(w in text for w in ("refactor", "architecture", "multi-step", "contract", "debug")):
            return ["claude", "openai", "groq", "gemini_pro", "ollama"]
        return ["groq", "openai", "gemini", "claude", "ollama"]
    return ["groq", "openai", "claude", "gemini", "ollama"]


def ask_best(prompt: str, *, task_type: str = "general", system: str | None = None,
             max_fallback_hops: int = 4) -> BrainResult:
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
