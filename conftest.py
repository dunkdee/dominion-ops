"""Repository-wide pytest import paths.

The full-suite gate runs `python -m pytest` from the repository root, where
pytest puts each test file's own directory on `sys.path` but nothing else.
Buddy modules import their siblings as `core.<module>` (the layout the
standalone runtime on the VM actually uses), and several suites import
`core.*` or `buddy_core.*` directly.

Declaring those roots once here is what lets the repository-wide suite see the
same import surface the runtime does, instead of each test file re-deriving it.
This adds import paths only — it registers no fixtures, skips nothing, and
hides no failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Order matters: the repository root first so `buddy_core.*` and `services.*`
# resolve, then buddy_core so the runtime's own `core.*` imports resolve.
for path in (ROOT, ROOT / "buddy_core"):
    entry = str(path)
    if path.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
