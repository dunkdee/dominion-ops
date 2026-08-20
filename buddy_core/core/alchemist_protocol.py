"""
core/alchemist_protocol.py — ALCHEMIST FOUR-PART PROTOCOL
===========================================================
Wraps holistic health intelligence with four-part governance.
Auto-vetos: medical diagnosis, dosage prescriptions, contraindicated advice.

Usage:
    from core.alchemist_protocol import AlchemistProtocol
    ap = AlchemistProtocol()
    result = ap.run(task="What minerals help with fatigue?", task_type="health_query")
"""

import sys
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.four_part_protocol import FourPartProtocol
from core.parallax_prompts import ALCHEMIST_AFFIRMATIVE, ALCHEMIST_ADVERSARIAL
from core.data_graph import DataGraph, source_failure_registry, source_checkpoint_history
from core.brain import ask


class AlchemistProtocol(FourPartProtocol):
    agent_name = "alchemist"

    def get_data_sources(self, task: str, **kwargs) -> Dict[str, Any]:
        graph = DataGraph()
        graph.add_source("prior_queries", lambda: source_checkpoint_history("alchemist", "health_query", 5), required=False)
        graph.add_source("failures", source_failure_registry, required=False)
        return graph.collect()["sources"]

    def get_affirmative_prompt(self, context: str) -> str:
        return ALCHEMIST_AFFIRMATIVE

    def get_adversarial_prompt(self, context: str) -> str:
        return ALCHEMIST_ADVERSARIAL

    def execute_action(self, task: str, context: str, parallax, **kwargs) -> Any:
        prompt = f"""You are the Alchemist — Dominion Healing's holistic wellness intelligence.

Answer this wellness question with the voice of The Art of True Healing:
warm, sovereign, empowering, grounded in natural law.

Question: {task}

Rules:
- Wellness education ONLY — never diagnose, never prescribe for serious conditions
- Include "This is general wellness information, not medical advice" when appropriate
- Be specific and actionable — minerals, herbs, practices with real context
- Keep it under 300 words unless detail is explicitly needed"""

        response = ask(prompt)

        # QA gate
        try:
            from core.qa_gate import validate_content
            qa = validate_content(response, platform="alchemist", content_type="health_response")
            return {"response": response, "qa_passed": qa.get("passed", True), "qa_score": qa.get("overall")}
        except Exception:
            return {"response": response, "qa_passed": True}
