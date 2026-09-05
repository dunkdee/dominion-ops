"""Buddy core package initialization.

Every BuddyOperator instance receives reviewed runtime extensions for capability
health, governed MCP access, and standing-authorized self-healing. The patch is
idempotent and leaves the base operator implementation intact.
"""
from __future__ import annotations

from pathlib import Path

from . import authorization as _authorization
from . import operator as _operator
from .operator_extensions import install_operator_extensions


def _strict_checkout_root(start: Path | None = None) -> Path | None:
    """Recognize a real Dominion checkout without mistaking $HOME for one.

    Production intentionally keeps a copied ``~/buddy_core`` runtime beside
    other home-directory state. A home directory that happens to contain
    ``.github`` and ``buddy_core`` is not enough evidence that the whole home
    directory is a repository checkout. Requiring the canonical repository
    marker set preserves the security boundary for source snapshots while
    allowing machine-local keys under ``~/.dominion``.
    """
    current = (start or Path(_authorization.__file__)).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=False)
        markers = (
            candidate / ".github",
            candidate / "buddy_core",
            candidate / "governance",
            candidate / "tests",
        )
        if all(marker.exists() for marker in markers):
            return candidate.resolve(strict=False)
    return None


# The authorization ledger is imported by operator.py before BuddyOperator is
# instantiated. Replace only its checkout detector with the stricter runtime-
# safe detector; all key-path, permission, HMAC, replay, and payload-binding
# enforcement remains inside authorization.py unchanged.
_authorization._detect_checkout_root = _strict_checkout_root


if not getattr(_operator.BuddyOperator, "_dominion_init_extended", False):
    _original_init = _operator.BuddyOperator.__init__

    def _extended_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        install_operator_extensions(self)

    _operator.BuddyOperator.__init__ = _extended_init
    _operator.BuddyOperator._dominion_init_extended = True


__all__ = ["install_operator_extensions"]
