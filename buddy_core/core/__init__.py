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
    """Return only a real Git checkout root.

    The production Buddy runtime is a governed copy at ``~/buddy_core`` while
    the canonical repository is the separate ``~/dominion-ops`` checkout.
    Home may legitimately contain repo-like directories such as ``.github``,
    ``governance`` and ``tests``; those names are not evidence that HOME itself
    is source-controlled. Treating them as checkout markers incorrectly puts
    the approved machine-local ``~/.dominion`` key state inside a fake repo.

    A real checkout is identified by Git metadata. The authorization module
    separately rejects any key path inside the Buddy source tree itself, so
    removing directory-name heuristics does not permit a key under source.
    """
    current = (start or Path(_authorization.__file__)).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=False)
    return None


# Install the runtime-safe checkout detector before any BuddyOperator instance
# is created. Authorization key-path, permission, HMAC, replay, payload-binding,
# and fail-closed enforcement in authorization.py remain unchanged.
_authorization._detect_checkout_root = _strict_checkout_root


if not getattr(_operator.BuddyOperator, "_dominion_init_extended", False):
    _original_init = _operator.BuddyOperator.__init__

    def _extended_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        install_operator_extensions(self)

    _operator.BuddyOperator.__init__ = _extended_init
    _operator.BuddyOperator._dominion_init_extended = True


__all__ = ["install_operator_extensions"]
