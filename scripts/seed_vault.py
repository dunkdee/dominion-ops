#!/usr/bin/env python3
"""Retired legacy Obsidian vault seeder.

The governed Dominion Brain is rendered by scripts/render_dominion_brain.py and
published through .github/workflows/publish-dominion-brain-production.yml.
This compatibility path intentionally performs no filesystem mutation.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("LEGACY_VAULT_SEEDER=RETIRED mutation=none")
    print("Use scripts/render_dominion_brain.py for staged rendering.")
    print("Use Publish Dominion Brain — Production for governed production publication.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
