"""
utils/safe_io.py — Dominion Healing Ecosystem
==============================================
Canonical safe I/O helpers. Every agent MUST use these instead of
rolling their own open("w") or metadata dicts.

WHY THIS EXISTS
---------------
Two systemic bugs burned the ecosystem in April 2026:
  1. metadata={{...}} — double braces created a set-containing-dict
     → TypeError: unhashable type at runtime, silently killed PhiMemory
  2. open(FILE, "w") — non-atomic write corrupted JSON mid-write
     under concurrent agent execution

These helpers make both bugs structurally impossible:
  - atomic_json_write()  → always uses tmp + os.replace()
  - phi_store()          → correct metadata dict, every time

USAGE (copy into any agent)
----------------------------
    from utils.safe_io import atomic_json_write, phi_store

    atomic_json_write(OUTPUT_FILE, results)
    phi_store(_memory, _AGENT, _vec(_result), _result)
"""

import os
import json
import tempfile
from datetime import datetime
from pathlib import Path


# ── Atomic JSON write ──────────────────────────────────────────────────────────

def atomic_json_write(path, data, indent: int = 2, default=None):
    """
    Write `data` to `path` as JSON atomically (tmp file → os.replace).
    Guarantees: the file is either fully written or unchanged.
    Never leaves a half-written file.

    Args:
        path    — str or Path to target file
        data    — JSON-serialisable object
        indent  — JSON indent level (default 2)
        default — optional json serialiser for non-standard types (e.g. str)
    """
    path = str(path)
    tmp  = path + ".tmp"
    kwargs = {"indent": indent}
    if default is not None:
        kwargs["default"] = default
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, **kwargs)
    os.replace(tmp, path)


# ── PhiMemory store wrapper ────────────────────────────────────────────────────

def phi_store(memory_store, agent_name: str, vector: list, result=None, extra: dict = None):
    """
    Store an agent result in PhiMemory with correct metadata.
    Replaces the copy-pasted metadata={{...}} pattern that caused
    TypeError: unhashable type across every agent.

    Args:
        memory_store  — the PhiMemory store (from phi_memory.get_store())
        agent_name    — string name of the agent (e.g. "email_sender")
        vector        — list[float] vector encoding of the result
        result        — the result object (for preview in metadata)
        extra         — optional dict of additional metadata fields
    """
    try:
        meta = {
            "agent": agent_name,
            "ts":    datetime.now().isoformat()[:19],
            "result_preview": str(result)[:120] if result is not None else "",
        }
        if extra:
            meta.update(extra)
        memory_store.store(agent_name, vector, metadata=meta)
    except Exception:
        pass   # PhiMemory failure must never crash an agent


# ── Load JSON safely ───────────────────────────────────────────────────────────

def load_json(path, default=None):
    """
    Load a JSON file. Returns `default` (empty list by default) on any error.
    Never raises — safe for use in pipeline agents.
    """
    if default is None:
        default = []
    try:
        p = Path(path)
        if p.exists() and p.stat().st_size > 2:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default
