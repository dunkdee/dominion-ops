"""
core/proposal_protocol.py — PROPOSAL FOUR-PART PROTOCOL
=========================================================
Wraps proposal generation with four-part governance.
Checkpoint → Data Graph → Parallax → Final Review → QA Gate.

Usage:
    from core.proposal_protocol import ProposalProtocol
    pp = ProposalProtocol()
    result = pp.run(task=job_description, task_type="upwork_proposal")
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.four_part_protocol import FourPartProtocol
from core.parallax_prompts import PROPOSAL_AFFIRMATIVE, PROPOSAL_ADVERSARIAL
from core.data_graph import DataGraph, source_failure_registry, source_checkpoint_history
from core.brain import ask


class ProposalProtocol(FourPartProtocol):
    agent_name = "proposal_agent"

    def get_data_sources(self, task: str, **kwargs) -> Dict[str, Any]:
        graph = DataGraph()

        def parse_job_signals():
            """Extract signals from the job description."""
            lines = task.lower()
            return {
                "has_budget": "$" in task,
                "us_only": "united states only" in lines or "us only" in lines,
                "verified": "verified" in lines,
                "competition_hint": "proposals:" in lines,
                "word_count": len(task.split()),
            }

        graph.add_source("job_signals", parse_job_signals, required=True)
        graph.add_source("prior_proposals", lambda: source_checkpoint_history("proposal_agent", "upwork_proposal", 5), required=False)
        graph.add_source("failures", source_failure_registry, required=False)

        return graph.collect()["sources"]

    def get_affirmative_prompt(self, context: str) -> str:
        return PROPOSAL_AFFIRMATIVE

    def get_adversarial_prompt(self, context: str) -> str:
        return PROPOSAL_ADVERSARIAL

    def execute_action(self, task: str, context: str, parallax, **kwargs) -> Any:
        """Generate the proposal using brain.ask(), run through QA gate."""
        prompt = f"""Write a freelance proposal for this job:

JOB DESCRIPTION:
{task[:2000]}

Write as DeWayne Singleton — founder of Dominion Healing, an AI-powered sovereign wellness ecosystem.

Rules:
- Under 150 words
- Hook in the FIRST sentence
- Specific about deliverables
- Confident and direct
- End with clear next step
- Return ONLY the proposal text."""

        proposal_text = ask(prompt)

        # QA gate
        try:
            from core.qa_gate import validate_proposal
            qa = validate_proposal(proposal_text, platform=kwargs.get("platform", "upwork"))
            if not qa.get("passed", True):
                return {"status": "qa_rejected", "issues": qa.get("issues", []), "proposal": proposal_text}
        except Exception:
            pass

        # Voice inversion check
        inversion_flags = ["we are looking for", "we need", "we seek", "the ideal candidate",
                          "applicants should", "this role", "responsibilities include"]
        for flag in inversion_flags:
            if flag in proposal_text.lower():
                return {"status": "voice_inverted", "flag": flag, "proposal": proposal_text}

        return {"status": "approved", "proposal": proposal_text}
