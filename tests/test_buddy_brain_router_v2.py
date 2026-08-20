from buddy_core.core import brain_router


def test_coding_prefers_claude_and_includes_openai():
    order = brain_router.route_order("coding", "debug this repository")
    assert order[0] == "claude"
    assert "openai" in order
    assert "gemini_pro" in order
    assert "ollama" in order


def test_research_prefers_deep_synthesis_and_includes_openai():
    order = brain_router.route_order("research_synthesis", "compare current sources")
    assert order[0] == "gemini_pro"
    assert "claude" in order
    assert "openai" in order


def test_general_route_contains_openai_specialist_fallback():
    order = brain_router.route_order("general", "help me think through this")
    assert order[0] == "groq"
    assert "openai" in order


def test_openai_is_actually_callable_when_prior_brains_are_unavailable(monkeypatch):
    availability = {
        "claude": False,
        "groq": False,
        "gemini_pro": False,
        "gemini": False,
        "openai": True,
        "ollama": False,
    }
    calls = []
    monkeypatch.setattr(brain_router, "_available", lambda mode: availability.get(mode, False))
    monkeypatch.setattr(
        brain_router,
        "_call",
        lambda mode, prompt, system=None: calls.append(mode) or "openai result",
    )

    result = brain_router.ask_best("design this system", task_type="coding")
    assert result.provider == "openai"
    assert result.model == "gpt-4o-mini"
    assert result.text == "openai result"
    assert calls == ["openai"]


def test_no_paid_multi_provider_fanout_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(brain_router, "_available", lambda mode: mode in {"groq", "openai", "claude"})
    monkeypatch.setattr(
        brain_router,
        "_call",
        lambda mode, prompt, system=None: calls.append(mode) or f"{mode} result",
    )

    result = brain_router.ask_best("summarize this", task_type="general")
    assert result.provider == "groq"
    assert calls == ["groq"]
