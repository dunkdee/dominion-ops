import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _claim_app_package(app_root):
    """Ensure `app` resolves to THIS subproject.

    Two deployable subprojects in this repository each provide a top-level
    `app` package (OPS/radah-traffic-engine and apps/video-studio). Under a
    repository-wide pytest run whichever imports first wins, and the other
    collects against the wrong package. Each suite claims its own `app` before
    its tests import, which makes repo-wide collection order-independent
    without renaming either deployed package.
    """
    import sys
    entry = str(app_root)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    existing = sys.modules.get("app")
    owned = getattr(existing, "__file__", "") or ""
    if existing is not None and not owned.startswith(entry):
        for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
            del sys.modules[name]


_claim_app_package(ROOT)
