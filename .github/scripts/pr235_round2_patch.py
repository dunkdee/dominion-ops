from pathlib import Path
import textwrap


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    count = src.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    p.write_text(src.replace(old, new, 1), encoding="utf-8")


# A. Governance validator: replace formatting-sensitive substring checks with AST semantics.
validator = "scripts/validate_elite_governance.py"
insert_before = "def collect_failures() -> list[dict]:\n"
semantic_helpers = r'''def _subscript_key(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    value = node.slice
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def autopilot_productivity_semantics(source: str) -> tuple[bool, str]:
    """Verify progress timestamps are guarded by productive_complete(receipt).

    AST inspection makes this invariant independent of whitespace, quote style,
    comments, and harmless formatting changes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return False, f"autopilot source is not valid Python: {exc.msg}"

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    productive = functions.get("productive_complete")
    persist = functions.get("persist_cycle")
    if productive is None or persist is None:
        return False, "productive_complete/persist_cycle enforcement function missing"

    productive_constants = {
        node.value for node in ast.walk(productive)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if "COMPLETE" not in productive_constants or "HELD" in productive_constants:
        return False, "productive_complete does not exclusively model COMPLETE outcomes"

    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(persist):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    guarded_keys: set[str] = set()
    tracked = {"last_progress_at", "last_productive_at"}
    for node in ast.walk(persist):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            key = _subscript_key(target)
            if key not in tracked:
                continue
            cursor = parent.get(node)
            guarded = False
            while cursor is not None and cursor is not persist:
                if isinstance(cursor, ast.If):
                    test = cursor.test
                    if (
                        isinstance(test, ast.Call)
                        and isinstance(test.func, ast.Name)
                        and test.func.id == "productive_complete"
                        and len(test.args) == 1
                        and isinstance(test.args[0], ast.Name)
                        and test.args[0].id == "receipt"
                    ):
                        guarded = True
                        break
                cursor = parent.get(cursor)
            if not guarded:
                return False, f"{key} can be written without productive_complete(receipt)"
            guarded_keys.add(key)

    if guarded_keys != tracked:
        missing = ", ".join(sorted(tracked - guarded_keys))
        return False, f"productive timestamp assignment missing: {missing}"
    return True, "ok"


'''
replace_once(validator, insert_before, semantic_helpers + insert_before)

replace_once(
    validator,
    '''    autopilot = read(AUTOPILOT)\n    if 'if bounded_cycle_ok(receipt):\\n        lane_state["last_progress_at"]' in autopilot:\n        failures.append({\n            "gate": "truthful_progress",\n            "reason": "autopilot marks structurally-valid HELD/BLOCKED cycles as progress",\n        })\n    if 'receipt["status"] in {"COMPLETE", "HELD"}' in autopilot:\n        failures.append({\n            "gate": "truthful_productivity",\n            "reason": "autopilot marks HELD as productive",\n        })\n''',
    '''    autopilot = read(AUTOPILOT)\n    autopilot_safe, autopilot_reason = autopilot_productivity_semantics(autopilot)\n    if not autopilot_safe:\n        failures.append({\n            "gate": "truthful_progress",\n            "reason": autopilot_reason,\n        })\n''',
)

# B. Held-plan persistence: make the rename crash-durable on POSIX.
replace_once(
    "buddy_core/core/operator.py",
    '''            os.replace(tmp, path)\n            try:\n                path.chmod(0o600)\n            except OSError:\n                pass\n''',
    '''            os.replace(tmp, path)\n            if os.name == "posix":\n                dir_fd = None\n                try:\n                    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)\n                    dir_fd = os.open(str(path.parent), flags)\n                    os.fsync(dir_fd)\n                except (OSError, NotImplementedError) as exc:\n                    raise AuthorizationError("held_plan_directory_fsync_failed") from exc\n                finally:\n                    if dir_fd is not None:\n                        try:\n                            os.close(dir_fd)\n                        except OSError:\n                            pass\n            try:\n                path.chmod(0o600)\n            except OSError:\n                pass\n''',
)

# C. Regression coverage for both current-head independent-review blockers.
Path("tests/test_pr235_final_review_round2.py").write_text(textwrap.dedent(r'''\
"""Regression coverage for PR #235 current-head independent-review round two."""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "buddy_core"))

from core import operator as operator_mod  # noqa: E402
from core.authorization import AuthorizationError  # noqa: E402
from core.operator import BuddyOperator  # noqa: E402


def _load_validator():
    path = ROOT / "scripts" / "validate_elite_governance.py"
    spec = importlib.util.spec_from_file_location("elite_governance_round2", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GovernanceFormattingResistanceTests(unittest.TestCase):
    def test_current_autopilot_passes_semantic_gate(self):
        validator = _load_validator()
        source = (ROOT / "scripts" / "autopilot" / "lane_supervisor.py").read_text(encoding="utf-8")
        ok, reason = validator.autopilot_productivity_semantics(source)
        self.assertTrue(ok, reason)

    def test_whitespace_and_single_quote_bypass_is_rejected(self):
        validator = _load_validator()
        unsafe = '''
def productive_complete(receipt):
    return receipt.get('status') == 'COMPLETE'

def persist_cycle(receipt, lane_state, now):
    if bounded_cycle_ok ( receipt ) :
        lane_state [ 'last_progress_at' ] = now
        lane_state [ 'last_productive_at' ] = now
'''
        ok, reason = validator.autopilot_productivity_semantics(unsafe)
        self.assertFalse(ok)
        self.assertIn("without productive_complete", reason)

    def test_held_cannot_be_declared_productive_by_helper(self):
        validator = _load_validator()
        unsafe = '''
def productive_complete(receipt):
    return receipt.get("status") in {"COMPLETE", "HELD"}

def persist_cycle(receipt, lane_state, now):
    if productive_complete(receipt):
        lane_state["last_progress_at"] = now
        lane_state["last_productive_at"] = now
'''
        ok, reason = validator.autopilot_productivity_semantics(unsafe)
        self.assertFalse(ok)
        self.assertIn("exclusively", reason)


class HeldPlanDurabilityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "parent-directory fsync is a POSIX durability boundary")
    def test_held_plan_parent_directory_fsync_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            operator = BuddyOperator(state_dir=Path(tmp))
            real_fsync = operator_mod.os.fsync

            def guarded_fsync(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError("simulated held-plan directory fsync failure")
                return real_fsync(fd)

            with mock.patch.object(operator_mod.os, "fsync", side_effect=guarded_fsync):
                with self.assertRaisesRegex(AuthorizationError, "held_plan_directory_fsync_failed"):
                    operator._persist_held_plan(
                        "approval_aaaaaaaaaaaa",
                        {"mission_id": "durability", "step": {"capability": "external.publish"}},
                    )


if __name__ == "__main__":
    unittest.main()
'''), encoding="utf-8")

for helper in (
    ".github/scripts/pr235_round2_patch.py",
    ".github/workflows/pr235-round2-final-closure.yml",
):
    helper_path = Path(helper)
    if helper_path.exists():
        helper_path.unlink()

print("PR235_FINAL_REVIEW_ROUND2=APPLIED")
