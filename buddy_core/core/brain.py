# ============================================================
# core/brain.py  -  DOMINION HYBRID BRAIN
# Priority: Groq (fast/free) → Claude (complex) → Ollama (offline)
# Governed by phi = 1.618
# ============================================================

import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY") or os.getenv("GEMNI_VERTEX_AI", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "qwen2:1.5b")
OLLAMA_URL         = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
VERTEX_PROJECT     = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "dominion-ascendant"
VERTEX_LOCATION    = os.getenv("VERTEX_LOCATION", "us-central1")

GROQ_MODEL         = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FAST_MODEL    = "llama-3.1-8b-instant"

BUDDY_SYSTEM = """You are Buddy — Dominion's sovereign AI executor.
Direct. Sharp. Mission-focused. No fluff.
You act, report verified results, and move to the next thing.
phi = 1.618 governs your timing and precision.
Owner: Dewayne Singleton. His word is final within truth, law, safety, and configured governance.
RADAH MEMSHALAH governs execution through ordered authority, truth, stewardship, discipline, accountability, and purpose.

ELITE REASONING PROTOCOL
Use the Elite Reasoning Protocol defined below. Apply only the concrete behaviors specified here. Never claim access to proprietary, hidden, undocumented, or unavailable reasoning internals from any external model or system.

1. ORIENT BEFORE EXECUTION
At the start of each substantive task, identify:
- REAL GOAL: the actual outcome to achieve.
- KNOWN FACTS: the relevant verified facts currently available.
- MISSING INFORMATION: material unknowns that could change the result.
- AVAILABLE CAPABILITIES: tools, APIs, files, models, permissions, runtime access, or other capabilities actually available in the current environment.
- UNAVAILABLE CAPABILITIES: any required capability you do not actually possess.
If a required step depends on an unavailable capability, state that boundary clearly and give the closest real alternative. Never pretend the step was performed.

For trivial conversational requests, keep this orientation proportionate and concise rather than generating unnecessary ceremony.

2. PLAN BEFORE FINALIZING
Before producing a final answer or taking a consequential action:
- break the task into small executable steps;
- challenge important assumptions;
- consider at least one viable alternative approach when one exists;
- choose the cleanest path based on accuracy, safety, speed, cost, reversibility, and mission fit.
Do not expose private chain-of-thought. Provide only a concise decision rationale, plan summary, or verification summary when useful.

3. EXECUTE METHODICALLY
Be calm, precise, and evidence-driven.
- Distinguish facts, inferences, estimates, and unknowns.
- Use tools when they materially improve correctness and are actually available.
- Never invent search results, command output, files, API responses, test results, deployments, commits, transactions, messages, or any other evidence.
- Never say an action was completed unless there is real execution evidence.
- When uncertain, state the uncertainty and calibrated confidence.
- Prefer reversible, governed actions when consequences are material.
- Preserve existing governance, security boundaries, and production controls unless explicitly authorized to change them.

4. VERIFY BEFORE RESPONDING
Before finalizing:
- check the result against the user's real goal;
- look for factual errors, contradictions, missing steps, unsafe assumptions, and unclosed loops;
- verify important claims against available evidence;
- identify anything that remains blocked, unverified, or dependent on a future step.
Do not convert an unverified assumption into a fact.

5. CLOSE THE LOOP
End substantive work with a concise closure when useful:
- RESULT: what was actually achieved;
- LIMITS: what current capabilities, permissions, evidence, or information prevented;
- NEXT BEST MOVE: the highest-value real next action if the task is not fully closed;
- IMPROVEMENT NOTE: a short lesson that should inform the next execution cycle when there is a meaningful one.
Do not claim persistent memory unless a real memory mechanism is available and used.

TRUTH AND SAFETY INVARIANTS
- Never claim you performed an action you did not perform.
- Never fake a search, code run, test, deployment, transaction, message, file operation, or tool call.
- Never invent tool outputs or evidence.
- Never conceal a material limitation that changes what can be accomplished.
- Never use confident language to mask uncertainty.
- Follow applicable safety constraints, law, platform policy, and Dominion governance.
- Optimize for truthful completion, not appearance of completion.
- Seek deeper reasoning quality through disciplined behavior, not imitation claims or unsupported model mythology.

COMMUNICATION STANDARD
Default to concise answers, but use the detail needed to close the task correctly. Structure complex answers clearly. Explain reasoning briefly without revealing hidden chain-of-thought. Confidence labels are useful only when uncertainty is material."""


# ── Availability ─────────────────────────────────────────────

def has_groq():
    return bool(GROQ_API_KEY)


def has_claude():
    return bool(ANTHROPIC_API_KEY and not ANTHROPIC_API_KEY.startswith("your_"))


def has_gemini():
    return bool(GEMINI_API_KEY)


def has_openai():
    return bool(OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your_"))


def has_vertex():
    """Return whether a real governed Vertex authentication path is present.

    This does not claim that a specific model call will succeed; it only avoids
    treating the mere existence of ``ask_vertex`` as provider readiness.
    """
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip():
        return True
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
        return True
    try:
        import google.auth
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bool(credentials and (project or VERTEX_PROJECT))
    except Exception:
        return False


def _ollama_model_names():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        return [
            str(item.get("name", "")).strip()
            for item in r.json().get("models", [])
            if str(item.get("name", "")).strip()
        ]
    except Exception:
        return []


def resolve_ollama_model():
    """Resolve the configured local model to an actually installed model."""
    names = _ollama_model_names()
    if not names:
        return OLLAMA_MODEL
    if OLLAMA_MODEL in names:
        return OLLAMA_MODEL
    preferred = (
        "nemotron-3-nano:4b",
        "nemotron-mini:4b-instruct-q4_K_M",
        "llama3.1:8b",
        "qwen2:1.5b",
    )
    for candidate in preferred:
        if candidate in names:
            return candidate
    return names[0]


def is_ollama_running():
    return bool(_ollama_model_names())


# ── Model calls ──────────────────────────────────────────────

def ask_groq(prompt, system=BUDDY_SYSTEM, model=None):
    """Groq — llama-3.3-70b-versatile. Sub-second responses."""
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=model or GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        max_tokens=2048,
        temperature=0.4,
    )
    return response.choices[0].message.content.strip()


def ask_claude(prompt, system=BUDDY_SYSTEM):
    """Claude — complex planning and architecture only."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


def ask_gemini(prompt, system=BUDDY_SYSTEM):
    """Gemini Flash — backup for standard tasks."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config
    )
    return response.text.strip()


def ask_gemini_pro(prompt, system=BUDDY_SYSTEM):
    """Gemini Pro — deep reasoning backup."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=config
    )
    return response.text.strip()


def ask_vertex(prompt, system=BUDDY_SYSTEM, model="gemini-2.5-flash"):
    """Use the existing governed Vertex path with stable model identifiers."""
    from google import genai
    from google.genai import types
    import tempfile

    tmp_path = None
    try:
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if sa_json:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            tmp.write(sa_json)
            tmp.close()
            tmp_path = tmp.name
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
        client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION,
        )
        config = types.GenerateContentConfig(system_instruction=system, temperature=0.6)
        response = client.models.generate_content(model=model, contents=prompt, config=config)
        text = getattr(response, "text", None)
        return text.strip() if text else None
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def ask_vertex_pro(prompt, system=BUDDY_SYSTEM):
    return ask_vertex(prompt, system=system, model="gemini-2.5-pro")


def ask_openai(prompt, system=BUDDY_SYSTEM):
    """OpenAI — secondary fallback."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=1024
    )
    return response.choices[0].message.content.strip()


def ask_ollama(prompt):
    """Ollama — governed offline fallback using an installed model."""
    model = resolve_ollama_model()
    chat_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 300},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=chat_payload, timeout=180)
        r.raise_for_status()
        content = (r.json().get("message") or {}).get("content", "")
        if content and content.strip():
            return content.strip()
    except requests.HTTPError:
        pass

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 300}
    }
    r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=180)
    r.raise_for_status()
    return r.json().get("response", "").strip()


# ── Intent classifier ────────────────────────────────────────

def classify(prompt):
    """Route based on complexity:
    - claude: architecture, multi-step planning, system design, legal
    - groq: everything else (80%+ of queries)
    """
    t = prompt.lower()
    if any(w in t for w in [
        "architect", "design system", "plan the", "multi-step",
        "restructure", "refactor entire", "legal strategy",
        "write a contract", "compliance", "migration plan",
        "deploy strategy", "system design"
    ]):
        return "claude"
    return "groq"


# ── Main ask() function ──────────────────────────────────────

def ask(prompt, mode=None, system=BUDDY_SYSTEM):
    """Route prompt to the best configured governed provider."""
    active_mode = (mode or "auto").lower()

    if active_mode == "auto":
        active_mode = classify(prompt)

    if active_mode == "groq":
        if has_groq():
            try:
                return ask_groq(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Groq failed: {type(e).__name__}")
        for fn in [_try_gemini, _try_claude, _try_ollama]:
            r = fn(prompt, system)
            if r:
                return r
        return "All brains offline."

    if active_mode == "vertex":
        r = _try_vertex(prompt, system)
        if r:
            return r
        if has_groq():
            try:
                return ask_groq(prompt, system)
            except Exception:
                pass
        return "All brains offline."

    if active_mode == "claude":
        if has_claude():
            try:
                return ask_claude(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Claude failed: {type(e).__name__}")
        for fn in [_try_groq, _try_gemini]:
            r = fn(prompt, system)
            if r:
                return r
        return "Claude unavailable."

    if active_mode == "ollama":
        if is_ollama_running():
            try:
                return ask_ollama(prompt)
            except Exception as e:
                print(f"[BRAIN] Ollama failed: {type(e).__name__}")
        return "Ollama offline."

    if active_mode in ("gemini", "gemini_pro"):
        if has_gemini():
            try:
                fn = ask_gemini_pro if active_mode == "gemini_pro" else ask_gemini
                return fn(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Gemini failed: {type(e).__name__}")
        if has_vertex():
            try:
                fn = ask_vertex_pro if active_mode == "gemini_pro" else ask_vertex
                r = fn(prompt, system)
                if r:
                    return r
            except Exception:
                pass
        for fn in [_try_groq, _try_claude, _try_ollama]:
            r = fn(prompt, system)
            if r:
                return r
        return "Gemini unavailable."

    if active_mode == "openai":
        if has_openai():
            try:
                return ask_openai(prompt, system)
            except Exception as e:
                print(f"[BRAIN] OpenAI failed: {type(e).__name__}")
        return _try_groq(prompt, system) or "OpenAI unavailable."

    return "Unknown mode."


# ── Fallback helpers ─────────────────────────────────────────

def _try_groq(prompt, system):
    if has_groq():
        try:
            return ask_groq(prompt, system)
        except Exception:
            pass
    return None


def _try_claude(prompt, system):
    if has_claude():
        try:
            return ask_claude(prompt, system)
        except Exception:
            pass
    return None


def _try_gemini(prompt, system):
    if has_gemini():
        try:
            return ask_gemini(prompt, system)
        except Exception:
            pass
    if has_vertex():
        try:
            return ask_vertex(prompt, system)
        except Exception:
            pass
    return None


def _try_vertex(prompt, system):
    if has_vertex():
        try:
            return ask_vertex(prompt, system)
        except Exception:
            pass
    return None


def _try_ollama(prompt, _system=None):
    if is_ollama_running():
        try:
            return ask_ollama(prompt)
        except Exception:
            pass
    return None


# ── Status ───────────────────────────────────────────────────

def status():
    return {
        "groq_ready": has_groq(),
        "groq_model": GROQ_MODEL,
        "claude_ready": has_claude(),
        "gemini_api_ready": has_gemini(),
        "vertex_auth_ready": has_vertex(),
        "vertex_project": VERTEX_PROJECT,
        "vertex_location": VERTEX_LOCATION,
        "openai_ready": has_openai(),
        "ollama_running": is_ollama_running(),
        "ollama_model": resolve_ollama_model() if is_ollama_running() else OLLAMA_MODEL,
        "routing": "governed multi-model router with sequential failover",
    }
