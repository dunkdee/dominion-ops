"""
core/qa_gate.py — DOMINION QA GATE
====================================
Real quality validation using LLM verification.
Every agent output passes through here before shipping.

Uses brain.ask() to actually evaluate content — not substring matching.
Checks: hallucination, completeness, brand alignment, platform fit.

Usage:
  from core.qa_gate import validate, validate_content, validate_code

  result = validate(content, content_type="social_post", platform="instagram")
  if result["passed"]:
      ship_it()
  else:
      fix_issues(result["issues"])
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brain import ask
from utils.safe_io import atomic_json_write, load_json

QA_LOG = Path(__file__).resolve().parent.parent / "qa_gate_log.json"

# ── Validation prompts ───────────────────────────────────────

CONTENT_VALIDATION_PROMPT = """You are a strict quality gate for Dominion Healing content.

Evaluate this {content_type} for {platform}:

---
{content}
---

Score each dimension 1-10 and provide a brief reason:

1. AUTHENTICITY: Does this sound like a real person wrote it? Not generic AI slop?
2. BRAND_FIT: Does it match Dominion Healing's voice? (Direct, sovereign, street-smart, practical)
3. VALUE: Does it provide actual value or is it filler?
4. PLATFORM_FIT: Is it formatted correctly for {platform}? (length, tone, structure)
5. NO_HALLUCINATION: Are all claims reasonable? No made-up statistics or fake citations?

Respond in EXACTLY this JSON format, nothing else:
{{"authenticity": {{"score": N, "reason": "..."}}, "brand_fit": {{"score": N, "reason": "..."}}, "value": {{"score": N, "reason": "..."}}, "platform_fit": {{"score": N, "reason": "..."}}, "no_hallucination": {{"score": N, "reason": "..."}}, "overall": N, "passed": true/false, "issues": ["issue1", "issue2"]}}

Rules:
- overall = average of all 5 scores
- passed = true if overall >= 7 AND no single score below 5
- issues = list any score below 7 with what's wrong
- Be harsh. Dominion standard is excellence, not "good enough"."""

CODE_VALIDATION_PROMPT = """You are a senior engineer reviewing code for the Dominion ecosystem.

Evaluate this code:

---
{content}
---

Check:
1. FUNCTIONAL: Will this code actually run without errors?
2. SECURITY: Any injection, XSS, credential leaks, or unsafe patterns?
3. CORRECTNESS: Does the logic do what it claims?
4. STYLE: Clean, readable, no unnecessary complexity?
5. PRODUCTION_READY: Error handling, edge cases, no hardcoded secrets?

Respond in EXACTLY this JSON format, nothing else:
{{"functional": {{"score": N, "reason": "..."}}, "security": {{"score": N, "reason": "..."}}, "correctness": {{"score": N, "reason": "..."}}, "style": {{"score": N, "reason": "..."}}, "production_ready": {{"score": N, "reason": "..."}}, "overall": N, "passed": true/false, "issues": ["issue1", "issue2"]}}

Rules:
- overall = average of all 5 scores
- passed = true if overall >= 7 AND security >= 8 AND no single score below 5
- Be harsh. No trash ships in Dominion."""

PROPOSAL_VALIDATION_PROMPT = """You are evaluating a freelance proposal for quality.

Proposal:
---
{content}
---

Target platform: {platform}

Check:
1. RELEVANCE: Does the proposal address the job requirements specifically?
2. CREDIBILITY: Does it demonstrate real expertise (not generic claims)?
3. HOOK: Does the opening grab attention in the first 2 sentences?
4. SPECIFICITY: Are there concrete details, numbers, or examples?
5. CTA: Is there a clear next step / call to action?

Respond in EXACTLY this JSON format, nothing else:
{{"relevance": {{"score": N, "reason": "..."}}, "credibility": {{"score": N, "reason": "..."}}, "hook": {{"score": N, "reason": "..."}}, "specificity": {{"score": N, "reason": "..."}}, "cta": {{"score": N, "reason": "..."}}, "overall": N, "passed": true/false, "issues": ["issue1", "issue2"]}}

Rules:
- overall = average of all 5 scores
- passed = true if overall >= 7 AND hook >= 6
- Be harsh. Generic proposals are trash."""


def _parse_qa_response(response: str) -> Dict:
    """Parse LLM JSON response, handling common formatting issues."""
    if not response:
        return {"passed": False, "overall": 0, "issues": ["No response from QA brain"], "parse_error": True}

    # Try to extract JSON from response
    text = response.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    return {"passed": False, "overall": 0, "issues": ["QA response was not valid JSON"], "parse_error": True, "raw": text[:200]}


def _log_result(content_type: str, platform: str, result: Dict):
    """Log QA result."""
    log = load_json(QA_LOG, default=[])
    log.append({
        "ts": datetime.utcnow().isoformat(),
        "type": content_type,
        "platform": platform,
        "passed": result.get("passed", False),
        "overall": result.get("overall", 0),
        "issues": result.get("issues", []),
    })
    if len(log) > 500:
        log = log[-500:]
    atomic_json_write(QA_LOG, log, default=str)


# ============================================================
# PUBLIC API
# ============================================================

def validate_content(content: str, platform: str = "general",
                     content_type: str = "social_post") -> Dict:
    """
    Validate content through LLM-powered QA gate.
    Returns dict with passed, overall score, and issues.
    """
    prompt = CONTENT_VALIDATION_PROMPT.format(
        content=content,
        content_type=content_type,
        platform=platform,
    )

    response = ask(prompt)
    result = _parse_qa_response(response)
    _log_result(content_type, platform, result)
    return result


def validate_code(code: str) -> Dict:
    """Validate code through LLM-powered QA gate."""
    prompt = CODE_VALIDATION_PROMPT.format(content=code)
    response = ask(prompt)
    result = _parse_qa_response(response)
    _log_result("code", "any", result)
    return result


def validate_proposal(proposal: str, platform: str = "upwork") -> Dict:
    """Validate a freelance proposal."""
    prompt = PROPOSAL_VALIDATION_PROMPT.format(
        content=proposal,
        platform=platform,
    )
    response = ask(prompt)
    result = _parse_qa_response(response)
    _log_result("proposal", platform, result)
    return result


def validate(content: str, content_type: str = "social_post",
             platform: str = "general") -> Dict:
    """
    Universal validate function. Routes to the right validator.
    """
    if content_type == "code":
        return validate_code(content)
    elif content_type in ("proposal", "pitch"):
        return validate_proposal(content, platform)
    else:
        return validate_content(content, platform, content_type)


def get_qa_stats() -> Dict:
    """Get QA pass/fail stats."""
    log = load_json(QA_LOG, default=[])
    if not log:
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}

    total = len(log)
    passed = sum(1 for e in log if e.get("passed"))
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "recent_issues": [e["issues"] for e in log[-5:] if e.get("issues")],
    }


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Dominion QA Gate")
    parser.add_argument("--content", type=str, help="Content to validate")
    parser.add_argument("--file", type=str, help="File to validate")
    parser.add_argument("--type", type=str, default="social_post", help="Content type")
    parser.add_argument("--platform", type=str, default="general", help="Platform")
    parser.add_argument("--stats", action="store_true", help="Show QA stats")
    args = parser.parse_args()

    if args.stats:
        stats = get_qa_stats()
        print(json.dumps(stats, indent=2))
    elif args.file:
        with open(args.file, "r") as f:
            content = f.read()
        ctype = "code" if args.file.endswith(".py") else args.type
        result = validate(content, ctype, args.platform)
        print(json.dumps(result, indent=2))
    elif args.content:
        result = validate(args.content, args.type, args.platform)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
