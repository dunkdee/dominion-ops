"""Canonical filesystem locations for the Dominion Publisher.

There is exactly one credential-vault fallback string, defined here. Every
other module resolves through this helper rather than repeating a default.

This exists because the writer and the reader once disagreed. configure_meta.py
fell back to ~/.dominion/publisher/credential-vault while service.py fell back
to DB_PATH.parent/credential-vault (~/DominionsArk/data/credential-vault). With
DOMINION_PUBLISHER_VAULT set -- which install_publisher.sh does, and
meta_control.sh sources -- both agreed and the split was invisible. Run
configure_meta directly without that environment and the Meta app credentials
land where the service will never read them: configured, and silently absent.

Resolution is deliberately done per call, not at import, so a caller or a test
can change the environment and get the new answer.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_STATE_ROOT = "DOMINION_PUBLISHER_STATE_ROOT"
ENV_VAULT_ROOT = "DOMINION_PUBLISHER_VAULT"

# The single source of truth. install_publisher.sh provisions this same layout
# and meta_control.sh honours the same state-root override.
DEFAULT_STATE_ROOT = "~/.dominion/publisher"
VAULT_DIR_NAME = "credential-vault"


def _expand(value: str) -> Path:
    return Path(value).expanduser()


def state_root() -> Path:
    """Machine-local Publisher state directory."""
    override = os.environ.get(ENV_STATE_ROOT, "").strip()
    return _expand(override or DEFAULT_STATE_ROOT)


def vault_root() -> Path:
    """The credential vault directory.

    $DOMINION_PUBLISHER_VAULT wins when set. Otherwise the canonical default,
    which is the path the installer provisions and the path configure_meta
    writes to, so writer and reader cannot drift apart.
    """
    override = os.environ.get(ENV_VAULT_ROOT, "").strip()
    return _expand(override) if override else state_root() / VAULT_DIR_NAME
