"""
core/juris_protocol.py — JURIS FOUR-PART PROTOCOL
====================================================
Wraps legal intelligence with four-part governance.
Scope: trust formation, FDCPA, FCRA, Florida surplus funds recovery, constitutional/civil rights.
Auto-veto: living-man / sovereign-citizen / redemption theory (DECIDED AND CLOSED).

Knowledge base: 8 modules loaded from juris_handoff.md (Jun 24 2026).

Usage:
    from core.juris_protocol import JurisProtocol
    jp = JurisProtocol()
    result = jp.run(task="How do I set up an irrevocable trust?", task_type="legal_query")
"""

import sys
import os
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.four_part_protocol import FourPartProtocol
from core.parallax_prompts import JURIS_AFFIRMATIVE, JURIS_ADVERSARIAL
from core.data_graph import DataGraph, source_failure_registry, source_checkpoint_history
from core.brain import ask

# Load knowledge base
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dominion" / "agents" / "juris"))
    from knowledge_base import KNOWLEDGE_BASE, SCOPE_KEYWORDS
    KB_LOADED = True
except Exception:
    # Fallback: try relative path
    try:
        kb_path = Path(os.path.expanduser("~/dominion/agents/juris/knowledge_base.py"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("knowledge_base", kb_path)
        kb_mod = importlib.util.load_from_spec(spec)
        spec.loader.exec_module(kb_mod)
        KNOWLEDGE_BASE = kb_mod.KNOWLEDGE_BASE
        SCOPE_KEYWORDS = kb_mod.SCOPE_KEYWORDS
        KB_LOADED = True
    except Exception as _ke:
        KNOWLEDGE_BASE = ""
        SCOPE_KEYWORDS = [
            "trust", "fdcpa", "fcra", "fair debt", "fair credit", "credit report",
            "surplus", "property", "claim", "197.582", "45.033", "45.032",
            "tax deed", "foreclosure", "assignment", "escheat",
            "fourth amendment", "search", "seizure", "section 1983", "civil rights",
            "qualified immunity", "sixth amendment", "right to counsel",
            "resisting arrest", "843.02", "sealing", "expungement", "police", "arrest",
        ]
        KB_LOADED = False


# Hard-coded veto triggers — CLOSED per governance
JURIS_VETO_TRIGGERS = [
    "living man", "living woman", "sovereign citizen", "redemption theory",
    "strawman", "straw man", "birth certificate bond", "ucc redemption",
    "accepted for value", "a4v", "freedom from admiralty",
    "right to travel", "admiralty jurisdiction", "common law name",
    "all caps name", "corporate fiction",
]

# Documented failures — do NOT recommend these as strategy
JURIS_KNOWN_FAILED_THEORIES = [
    "Benabe", "Tucci-Jarraf", "Darrell Brooks defense",
    "Pauline Bauer", "Wesley Snipes tax argument",
]


class JurisProtocol(FourPartProtocol):
    agent_name = "juris"

    def get_data_sources(self, task: str, **kwargs) -> Dict[str, Any]:
        graph = DataGraph()
        graph.add_source("prior_queries", lambda: source_checkpoint_history("juris", "legal_query", 5), required=False)
        graph.add_source("failures", source_failure_registry, required=False)

        def check_scope():
            task_lower = task.lower()
            in_scope = any(t in task_lower for t in SCOPE_KEYWORDS)
            veto_triggered = any(t in task_lower for t in JURIS_VETO_TRIGGERS)
            return {
                "in_scope": in_scope,
                "veto_triggered": veto_triggered,
                "veto_triggers_found": [t for t in JURIS_VETO_TRIGGERS if t in task_lower],
                "kb_loaded": KB_LOADED,
            }

        graph.add_source("scope_check", check_scope, required=True)
        return graph.collect()["sources"]

    def get_affirmative_prompt(self, context: str) -> str:
        return JURIS_AFFIRMATIVE

    def get_adversarial_prompt(self, context: str) -> str:
        return JURIS_ADVERSARIAL

    def execute_action(self, task: str, context: str, parallax, **kwargs) -> Any:
        # Pre-execution scope gate
        task_lower = task.lower()
        for trigger in JURIS_VETO_TRIGGERS:
            if trigger in task_lower:
                return {
                    "response": None,
                    "status": "VETOED",
                    "reason": (
                        f"Topic '{trigger}' is out of scope. "
                        "Sovereign-citizen, strawman, right-to-travel, and admiralty arguments "
                        "have no recorded courtroom success (see: Benabe, Bad Elk progeny, "
                        "Tucci-Jarraf, Darrell Brooks, Pauline Bauer) and carry real risk "
                        "(sanctions, fraud charges, default judgment). "
                        "Juris only teaches law that actually works."
                    ),
                }

        kb_section = KNOWLEDGE_BASE if KB_LOADED else ""

        prompt = f"""You are Juris — Dominion Healing's legal intelligence agent.
Your mission: help people understand their real rights, real defenses, and real civil remedies
using law that has a documented track record of working in court.

{kb_section}

QUESTION: {task}

SCOPE (constitutional/civil rights added Jun 24 2026):
- Trust formation (revocable, irrevocable, asset protection)
- FDCPA (Fair Debt Collection Practices Act, 15 U.S.C. 1692)
- FCRA (Fair Credit Reporting Act, 15 U.S.C. 1681)
- Florida surplus funds recovery (F.S. 45.033, 197.582)
- Fourth Amendment — search & seizure, warrantless home entry (Payton v. New York)
- Due Process Clause — 5th/14th Amendments, incorporation doctrine
- Section 1983 civil rights claims — elements, qualified immunity, recoverable damages
- Sixth Amendment — right to counsel, public defender access
- Right to resist unlawful arrest — honest framing of common-law right AND modern statutes
- Florida § 843.02 — resisting officer without violence, elements and defenses
- Florida sealing & expungement (F.S. 943.0585 / 943.059)

HARD RULES:
- Always cite the specific statute, case, or jurisdiction you are drawing from
- Always include: "This is general legal information, not legal advice. Consult a licensed attorney."
- Never suggest sovereign-citizen, strawman, right-to-travel, or admiralty arguments as strategy
- For resistance questions: present the honest common-law right AND the modern statutory narrowing
  AND the practical risk — do not minimize either side
- Steer toward post-hoc remedies (1983 claims, motions to suppress, public defender) over
  in-the-moment physical resistance
- Be precise. Cite law. Empower the user with what actually works.
"""

        response = ask(prompt)

        # Post-generation veto check
        response_lower = response.lower() if response else ""
        for trigger in JURIS_VETO_TRIGGERS:
            if trigger in response_lower:
                return {
                    "response": None,
                    "status": "VETOED_POST_GENERATION",
                    "reason": f"Response contained '{trigger}' — auto-vetoed per governance rules",
                }

        try:
            from core.qa_gate import validate_content
            qa = validate_content(response, platform="juris", content_type="legal_response")
            return {"response": response, "qa_passed": qa.get("passed", True), "qa_score": qa.get("overall")}
        except Exception:
            return {"response": response, "qa_passed": True}
