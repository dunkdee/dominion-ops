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
OLLAMA_URL         = "http://localhost:11434/api/generate"

GROQ_MODEL         = "llama-3.3-70b-versatile"
GROQ_FAST_MODEL    = "llama-3.1-8b-instant"

BUDDY_SYSTEM = """You are Buddy — Dominion's sovereign AI executor.
Direct. Sharp. Mission-focused. No fluff.
You act, report verified results, and move to the next thing.
phi = 1.618 governs your timing and precision.
Owner: Dewayne Singleton. His word is final within truth, law, safety, and configured governance.
RADAH MEMSHALAH governs execution through ordered authority, truth, stewardship, discipline, accountability, and purpose.

ELITE REASONING PROTOCOL
Use the reasoning discipline described below. It is inspired by the user's requested "Fable 5" structure, but you must never claim access to proprietary, hidden, or undocumented Fable 5 internals. Apply only the concrete behaviors defined here.

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

def is_ollama_running():
    try:
        r = requests.get("http://localhost:11434", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


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



def ask_vertex(prompt, system=BUDDY_SYSTEM, model='gemini-2.5-flash-preview-05-20'):
    try:
        from google import genai
        from google.genai import types
        import tempfile, os as _os
        sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')
        if sa_json:
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            tmp.write(sa_json)
            tmp.close()
            _os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = tmp.name
        client = genai.Client(vertexai=True, project='dominion-ascendant', location='us-central1')
        config = types.GenerateContentConfig(system_instruction=system, temperature=0.6)
        response = client.models.generate_content(model=model, contents=prompt, config=config)
        return response.text.strip()
    except Exception as e:
        return None

def ask_vertex_pro(prompt, system=BUDDY_SYSTEM):
    return ask_vertex(prompt, system=system, model='gemini-2.5-pro-preview-06-05')
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
    """Ollama — offline fallback only."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 300}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json().get("response", "").strip()


# ── Intent classifier ────────────────────────────────────────

def classify(prompt):
    """Route based on complexity:
    - claude: architecture, multi-step planning, system design, legal
    - groq: everything else (80%+ of queries)
    """
    t = prompt.lower()
    # Claude for complex reasoning only
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
    """
    Route prompt to best available brain.
    Priority: Groq (primary) → Claude (complex) → Gemini → Ollama (offline)

    Routing:
      groq   = standard conversation, tasks, status (80%)
      claude = complex planning, architecture (15%)
      ollama = offline fallback (5%)
    """
    active_mode = (mode or "auto").lower()

    if active_mode == "auto":
        active_mode = classify(prompt)

    # ── Groq (PRIMARY — fast, free, 70B) ─────────────────────
    if active_mode == "groq":
        if has_groq():
            try:
                return ask_groq(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Groq failed: {e}")
        # Fallback: Gemini → Claude → Ollama
        for fn in [_try_gemini, _try_claude, _try_ollama]:
            r = fn(prompt, system)
            if r:
                return r
        return "All brains offline."

    # -- Vertex AI (content/analysis)
    if active_mode == 'vertex':
        r = _try_vertex(prompt, system)
        if r:
            return r
        if has_groq():
            try:
                return ask_groq(prompt, system)
            except Exception:
                pass
        return 'All brains offline.'

        # ── Claude (complex planning/architecture) ────────────────
    if active_mode == "claude":
        if has_claude():
            try:
                return ask_claude(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Claude failed: {e}")
        # Fallback: Groq → Gemini
        for fn in [_try_groq, _try_gemini]:
            r = fn(prompt, system)
            if r:
                return r
        return "Claude unavailable."

    # ── Ollama (offline only) ─────────────────────────────────
    if active_mode == "ollama":
        if is_ollama_running():
            try:
                return ask_ollama(prompt)
            except Exception as e:
                print(f"[BRAIN] Ollama failed: {e}")
        return "Ollama offline."

    # ── Explicit Gemini mode ──────────────────────────────────
    if active_mode in ("gemini", "gemini_pro"):
        if has_gemini():
            try:
                fn = ask_gemini_pro if active_mode == "gemini_pro" else ask_gemini
                return fn(prompt, system)
            except Exception as e:
                print(f"[BRAIN] Gemini failed: {e}")
        for fn in [_try_groq, _try_claude]:
            r = fn(prompt, system)
            if r:
                return r
        return "Gemini unavailable."

    # ── Explicit OpenAI mode ──────────────────────────────────
    if active_mode == "openai":
        if has_openai():
            try:
                return ask_openai(prompt, system)
            except Exception as e:
                print(f"[BRAIN] OpenAI failed: {e}")
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
        "groq_ready":     has_groq(),
        "groq_model":     GROQ_MODEL,
        "claude_ready":   has_claude(),
        "gemini_ready":   has_gemini(),
        "openai_ready":   has_openai(),
        "ollama_running": is_ollama_running(),
        "ollama_model":   OLLAMA_MODEL,
        "routing":        "groq=primary, claude=complex, ollama=offline",
    }
