"""
core/four_part_protocol.py — DOMINION FOUR-PART PROTOCOL
=========================================================
Unified governance base class for every agent in the ecosystem.

Every decision runs through four stages:
  1. CHECKPOINT — load prior decision log, resume from crash
  2. DATA GRAPH — parallel multi-source data collection
  3. PARALLAX — affirmative vs adversarial debate
  4. FINAL REVIEW — risk gate, registry checks, GO verification

Based on TradingAgents governance architecture (arXiv:2412.20138),
wired with phi timing, SMC logic, and self-correcting memory.

Usage:
    from core.four_part_protocol import FourPartProtocol

    class MyAgent(FourPartProtocol):
        agent_name = "my_agent"
        def get_data_sources(self, task): ...
        def get_affirmative_prompt(self, context): ...
        def get_adversarial_prompt(self, context): ...
        def execute_action(self, decision): ...
"""

import os
import sys
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brain import ask
from utils.safe_io import atomic_json_write, load_json
from phi_constants import PHI

# Directories
BUDDY_CORE = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = BUDDY_CORE / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)

# Registries
FAILURE_REGISTRY = BUDDY_CORE / "failure_registry.json"
CLAIMS_REGISTRY = BUDDY_CORE / "claims_registry.json"
LICENSING_REGISTRY = BUDDY_CORE / "licensing_registry.json"
PRICE_REGISTRY = BUDDY_CORE / "price_registry.json"


def _task_hash(task_description: str) -> str:
    """Deterministic hash for a task — used as checkpoint key."""
    return hashlib.sha256(task_description.encode()).hexdigest()[:16]


# ============================================================
# PART 1 — CHECKPOINT
# ============================================================

class Checkpoint:
    """Load/save decision state for crash recovery and learning."""

    def __init__(self, agent_name: str):
        self.agent_dir = CHECKPOINT_DIR / agent_name
        self.agent_dir.mkdir(parents=True, exist_ok=True)

    def load(self, task_hash: str) -> Optional[Dict]:
        """Load prior run for this task. Returns None if no prior."""
        path = self.agent_dir / f"{task_hash}.json"
        if not path.exists():
            return None
        return load_json(path, default=None)

    def save(self, task_hash: str, state: Dict):
        """Persist checkpoint state."""
        state["saved_at"] = datetime.utcnow().isoformat()
        atomic_json_write(self.agent_dir / f"{task_hash}.json", state, default=str)

    def get_prior_outcomes(self, task_type: str, limit: int = 10) -> List[Dict]:
        """Get prior outcomes for similar task types (for learning)."""
        outcomes = []
        for f in sorted(self.agent_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = load_json(f, default={})
                if data.get("task_type") == task_type:
                    outcomes.append(data)
                    if len(outcomes) >= limit:
                        break
            except Exception:
                pass
        return outcomes


# ============================================================
# PART 3 — PARALLAX (Debate)
# ============================================================

class ParallaxResult:
    """Structured result from the affirmative/adversarial debate."""

    def __init__(self, affirmative: Dict, adversarial: Dict):
        self.affirmative = affirmative
        self.adversarial = adversarial

        aff_conf = affirmative.get("confidence", 50)
        adv_conf = adversarial.get("confidence", 50)

        self.confidence_gap = abs(aff_conf - adv_conf)
        self.adversarial_veto = adv_conf > 85
        self.needs_escalation = self.confidence_gap < 10
        self.approved = not self.adversarial_veto and not self.needs_escalation

    def summary(self) -> Dict:
        return {
            "affirmative_position": self.affirmative.get("position"),
            "affirmative_confidence": self.affirmative.get("confidence"),
            "adversarial_position": self.adversarial.get("position"),
            "adversarial_confidence": self.adversarial.get("confidence"),
            "confidence_gap": self.confidence_gap,
            "adversarial_veto": self.adversarial_veto,
            "needs_escalation": self.needs_escalation,
            "approved": self.approved,
        }


def _parse_parallax_response(response: str) -> Dict:
    """Parse structured JSON from parallax agent response."""
    default = {"position": "unknown", "confidence": 50, "reasoning": response[:200], "key_risks": []}

    if not response:
        return default

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    return default


def run_parallax(context: str, affirmative_prompt: str, adversarial_prompt: str) -> ParallaxResult:
    """
    Execute the parallax debate. Two agents argue for/against the action.

    Returns ParallaxResult with approval status.
    """
    # Affirmative agent
    aff_full = f"""{affirmative_prompt}

CONTEXT:
{context[:3000]}

Respond in EXACTLY this JSON format:
{{"position": "for", "confidence": 0-100, "reasoning": "...", "key_risks": ["risk1", "risk2"]}}

Return ONLY the JSON. No other text."""

    # Adversarial agent
    adv_full = f"""{adversarial_prompt}

CONTEXT:
{context[:3000]}

Respond in EXACTLY this JSON format:
{{"position": "against", "confidence": 0-100, "reasoning": "...", "key_risks": ["risk1", "risk2"]}}

Return ONLY the JSON. No other text."""

    # Run both (sequential — could be parallelized with asyncio)
    aff_response = ask(aff_full)
    time.sleep(PHI)  # Phi-spaced between calls
    adv_response = ask(adv_full)

    aff_parsed = _parse_parallax_response(aff_response)
    adv_parsed = _parse_parallax_response(adv_response)

    return ParallaxResult(aff_parsed, adv_parsed)


# ============================================================
# PART 4 — FINAL REVIEW (Risk Gate)
# ============================================================

def final_review(decision: Dict, agent_name: str, task_type: str) -> Dict:
    """
    Run risk gate before any external action.
    Checks against all registries, failure log, and stop conditions.

    Returns: {approved: bool, confidence: int, reasons: [...], rollback_path: str}
    """
    reasons = []
    approved = True

    # 1. Check failure registry — is this action a known failure?
    failures = load_json(FAILURE_REGISTRY, default=[])
    action = decision.get("action", "")
    for f in failures:
        if f.get("action", "") == action or f.get("failure_mode", "") in action:
            reasons.append(f"KNOWN FAILURE: {f.get('failure_mode', '')} — {f.get('fix', '')}")
            approved = False

    # 2. Check claims registry — any claims in the output?
    if decision.get("has_claims"):
        claims = load_json(CLAIMS_REGISTRY, default={})
        claim_list = claims.get("claims", [])
        verified_ids = {c["claim_id"] for c in claim_list if c.get("verified_at")}
        for claim_id in decision.get("claim_ids", []):
            if claim_id not in verified_ids:
                reasons.append(f"UNVERIFIED CLAIM: {claim_id} not in claims_registry")
                approved = False

    # 3. Check licensing registry — any assets need clearance?
    if decision.get("has_assets"):
        licensing = load_json(LICENSING_REGISTRY, default={})
        assets = licensing.get("assets", licensing if isinstance(licensing, list) else [])
        cleared = {a.get("video_id") or a.get("asset_path") for a in assets if a.get("cleared_for_public")}
        for asset_id in decision.get("asset_ids", []):
            if asset_id not in cleared:
                reasons.append(f"UNLICENSED ASSET: {asset_id} not cleared in licensing_registry")
                approved = False

    # 4. Check price registry — prices match?
    if decision.get("check_prices"):
        prices = load_json(PRICE_REGISTRY, default={})
        products = prices.get("products", {})
        for sku, expected_price in decision.get("price_checks", {}).items():
            registry_price = products.get(sku, {}).get("price_usd")
            if registry_price and registry_price != expected_price:
                reasons.append(f"PRICE MISMATCH: {sku} registry={registry_price} vs expected={expected_price}")
                approved = False

    # 5. Stop condition check — does this require GO?
    stop_conditions = [
        "live_capital", "publish", "submit_proposal", "schema_change",
        "secret_rotation", "dns_change", "caddy_change", "delete",
    ]
    for sc in stop_conditions:
        if sc in task_type.lower() or sc in action.lower():
            if not decision.get("dewayne_go"):
                reasons.append(f"STOP CONDITION: '{sc}' requires explicit DeWayne GO (§2)")
                approved = False

    # 6. Rollback path defined?
    rollback = decision.get("rollback_path", "")
    if not rollback:
        reasons.append("NO ROLLBACK PATH defined — required by §3")

    confidence = decision.get("confidence", 50)
    if not approved:
        confidence = min(confidence, 30)

    return {
        "approved": approved,
        "confidence": confidence,
        "reasons": reasons,
        "rollback_path": rollback,
        "agent": agent_name,
        "task_type": task_type,
        "reviewed_at": datetime.utcnow().isoformat(),
    }


# ============================================================
# UNIFIED BASE CLASS
# ============================================================

class FourPartProtocol:
    """
    Base class for all Dominion agents.
    Subclasses implement the agent-specific methods.
    """
    agent_name = "base"

    def __init__(self):
        self.checkpoint = Checkpoint(self.agent_name)

    def run(self, task: str, task_type: str = "default", **kwargs) -> Dict:
        """
        Execute the full four-part protocol for a task.

        Returns: {outcome, decision, parallax, review, checkpoint}
        """
        thash = _task_hash(task)

        # ── PART 1: CHECKPOINT ──
        prior = self.checkpoint.load(thash)
        prior_outcomes = self.checkpoint.get_prior_outcomes(task_type, limit=5)

        checkpoint_context = ""
        if prior:
            checkpoint_context = f"\nPRIOR RUN (same task):\nOutcome: {prior.get('outcome')}\nReflection: {prior.get('reflection', 'none')}\n"
        if prior_outcomes:
            checkpoint_context += f"\nPRIOR SIMILAR TASKS ({len(prior_outcomes)} runs):\n"
            for po in prior_outcomes[:3]:
                checkpoint_context += f"- {po.get('outcome', 'unknown')}: {po.get('reflection', '')[:100]}\n"

        # ── PART 2: DATA GRAPH ──
        data_sources = self.get_data_sources(task, **kwargs)
        context = f"TASK: {task}\n\nDATA:\n"
        for source_name, source_data in data_sources.items():
            context += f"\n[{source_name}]: {json.dumps(source_data, default=str)[:1000]}\n"
        context += checkpoint_context

        # ── PART 3: PARALLAX ──
        aff_prompt = self.get_affirmative_prompt(context)
        adv_prompt = self.get_adversarial_prompt(context)
        parallax = run_parallax(context, aff_prompt, adv_prompt)

        # Check parallax result
        if parallax.adversarial_veto:
            result = {
                "outcome": "VETOED",
                "reason": f"Adversarial agent vetoed (confidence {parallax.adversarial.get('confidence')}): {parallax.adversarial.get('reasoning', '')[:200]}",
                "parallax": parallax.summary(),
                "review": None,
            }
            self._log_and_save(thash, task, task_type, result)
            return result

        if parallax.needs_escalation:
            result = {
                "outcome": "ESCALATE",
                "reason": f"Confidence gap < 20 (aff={parallax.affirmative.get('confidence')}, adv={parallax.adversarial.get('confidence')}). Needs DeWayne decision.",
                "parallax": parallax.summary(),
                "review": None,
            }
            self._log_and_save(thash, task, task_type, result)
            return result

        # ── PART 4: FINAL REVIEW ──
        decision = {
            "action": task_type,
            "confidence": parallax.affirmative.get("confidence", 50),
            "rollback_path": kwargs.get("rollback_path", "revert last checkpoint"),
            "has_claims": kwargs.get("has_claims", False),
            "has_assets": kwargs.get("has_assets", False),
            "check_prices": kwargs.get("check_prices", False),
            "dewayne_go": kwargs.get("dewayne_go", False),
        }
        review = final_review(decision, self.agent_name, task_type)

        if not review["approved"]:
            result = {
                "outcome": "BLOCKED",
                "reason": f"Final review blocked: {review['reasons']}",
                "parallax": parallax.summary(),
                "review": review,
            }
            self._log_and_save(thash, task, task_type, result)
            return result

        # ── EXECUTE ──
        try:
            action_result = self.execute_action(task, context, parallax, **kwargs)
            result = {
                "outcome": "SUCCESS",
                "action_result": action_result,
                "parallax": parallax.summary(),
                "review": review,
            }
        except Exception as e:
            result = {
                "outcome": "ERROR",
                "error": str(e),
                "parallax": parallax.summary(),
                "review": review,
            }

        self._log_and_save(thash, task, task_type, result)
        return result

    def _log_and_save(self, thash: str, task: str, task_type: str, result: Dict):
        """Save checkpoint and log to failure registry if needed."""
        # Save checkpoint
        self.checkpoint.save(thash, {
            "agent": self.agent_name,
            "task": task[:500],
            "task_type": task_type,
            "outcome": result.get("outcome"),
            "reflection": result.get("reason", result.get("error", "")),
            "parallax": result.get("parallax"),
            "review": result.get("review"),
        })

        # Log failures to failure registry
        if result["outcome"] in ("VETOED", "BLOCKED", "ERROR"):
            try:
                failures = load_json(FAILURE_REGISTRY, default=[])
                failures.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent": self.agent_name,
                    "action": task_type,
                    "failure_mode": result.get("reason", result.get("error", "unknown")),
                    "fix": "Four-part protocol prevented execution",
                    "prevented_by_rule_id": "four_part_protocol",
                })
                atomic_json_write(FAILURE_REGISTRY, failures, default=str)
            except Exception:
                pass

    # ── Subclass interface ──

    def get_data_sources(self, task: str, **kwargs) -> Dict[str, Any]:
        """Return dict of {source_name: data}. Override in subclass."""
        return {"task_input": task}

    def get_affirmative_prompt(self, context: str) -> str:
        """Return the affirmative agent system prompt. Override in subclass."""
        return "You argue FOR this action. Be specific about benefits and expected outcomes."

    def get_adversarial_prompt(self, context: str) -> str:
        """Return the adversarial agent system prompt. Override in subclass."""
        return "You argue AGAINST this action. Identify risks, failure modes, and reasons to wait."

    def execute_action(self, task: str, context: str, parallax: ParallaxResult, **kwargs) -> Any:
        """Execute the approved action. Override in subclass."""
        raise NotImplementedError("Subclass must implement execute_action()")
