#!/usr/bin/env bash
set -euo pipefail

# Retired legacy vault initializer.
#
# The old implementation created a competing top-level hierarchy (00-inbox,
# 10-research, and similar folders) beside the governed Dominion-Brain mirror.
# Work Order #94 requires the canonical renderer and publisher instead.
echo "LEGACY_VAULT_SETUP=RETIRED mutation=none"
echo "CANONICAL_BRAIN_RENDERER=scripts/render_dominion_brain.py"
echo "CANONICAL_BRAIN_PUBLISHER=.github/workflows/publish-dominion-brain-production.yml"
exit 2
