"""
Dominion Phi Engine
Golden ratio governs all timing, scoring, retry, and validation.
PHI = 1.618033988749895
"""
import time, hashlib
from datetime import datetime

PHI = 1.618033988749895
PHI_SEED = 1618033988749895 % (2**32)

def phi_cycle():
    return (time.time() * PHI) % 1

def phi_gate():
    c = phi_cycle()
    if c < 0.1: return "AUDIT"
    if c > 0.9: return "PRIORITY"
    return "FLOW"

def phi_sleep(base: float, failures: int = 0) -> float:
    return min(base * (PHI ** failures), 3600)

def phi_score(value: float, max_value: float) -> float:
    return (value / max_value) / PHI if max_value > 0 else 0.0

def phi_hash(data: str) -> str:
    return hashlib.sha256(
        f"{PHI_SEED}{data}".encode()
    ).hexdigest()[:16]

def phi_validate(agent: str, action: str, result: str) -> dict:
    return {
        "agent": agent,
        "action": action,
        "result": result,
        "phi_cycle": phi_cycle(),
        "phi_gate": phi_gate(),
        "phi_hash": phi_hash(f"{agent}{action}{result}"),
        "timestamp": datetime.utcnow().isoformat()
    }
