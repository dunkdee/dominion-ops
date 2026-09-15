import json
from pathlib import Path


def test_current_commercial_state_cannot_be_true_with_blocked_gates():
    state = json.loads(Path("governance/commercial_closure_current_state.json").read_text(encoding="utf-8"))
    blocked = [name for name, gate in state["gates"].items() if gate["status"] == "BLOCKED"]
    assert blocked
    assert state["commercial_ready"] is False
