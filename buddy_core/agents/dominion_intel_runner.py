"""
dominion_intel_runner.py — DominionIntel Master Orchestrator
Runs the full intelligence pipeline in sequence:
1. Core (collect signals + AI processing)
2. Content (generate + deploy SEO pages)
3. Trading (phi-weighted ticker signals)
4. Leads (buyer intent mining)
5. Obsidian (sync to vault)

Called by: dominion-intel.service (systemd)
Schedule:  05:00, 10:00, 15:00, 20:00 UTC via dominion-intel.timer
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

BASE     = Path.home() / "buddy_core"
LOG_FILE = BASE / "intel" / "intel_runner.log"
BASE.joinpath("intel").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [INTEL-RUNNER] %(levelname)s %(message)s"
)
log = logging.getLogger("intel_runner")

PHI = 1.618033988749895


def run_module(name: str, module_path: str) -> bool:
    """Import and run a DominionIntel module."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.run()
        log.info(f"[OK] {name} completed")
        return True
    except Exception as e:
        log.error(f"[FAIL] {name}: {e}")
        return False


def main():
    log.info("=" * 55)
    log.info("  DOMINIONINTEL PIPELINE START")
    log.info(f"  {datetime.now(timezone.utc).isoformat()}")
    log.info("=" * 55)

    agents_dir = BASE / "agents"
    pipeline = [
        ("intel_core",     str(agents_dir / "dominion_intel_core.py")),
        ("intel_content",  str(agents_dir / "dominion_intel_content.py")),
        ("intel_trading",  str(agents_dir / "dominion_intel_trading.py")),
        ("intel_leads",    str(agents_dir / "dominion_intel_leads.py")),
        ("intel_obsidian", str(agents_dir / "dominion_intel_obsidian.py")),
    ]

    results = {}
    for name, path in pipeline:
        print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Running {name}...")
        ok = run_module(name, path)
        results[name] = ok
        if not ok:
            log.warning(f"{name} failed — continuing pipeline")
        time.sleep(PHI)  # phi-governed timing between modules

    # Summary
    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed

    log.info(f"Pipeline complete: {passed} OK / {failed} failed")
    print(f"\n{'='*40}")
    print(f"  DominionIntel Pipeline: {passed}/{len(pipeline)} OK")
    for name, ok in results.items():
        print(f"  {'[OK]' if ok else '[FAIL]'} {name}")
    print(f"{'='*40}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
