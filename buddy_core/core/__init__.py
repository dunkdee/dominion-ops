"""Buddy core package initialization.

Every BuddyOperator instance receives reviewed runtime extensions for capability
health, governed MCP access, and standing-authorized self-healing. The patch is
idempotent and leaves the base operator implementation intact.
"""
from __future__ import annotations

from . import operator as _operator
from .operator_extensions import install_operator_extensions


if not getattr(_operator.BuddyOperator, "_dominion_init_extended", False):
    _original_init = _operator.BuddyOperator.__init__

    def _extended_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        install_operator_extensions(self)

    _operator.BuddyOperator.__init__ = _extended_init
    _operator.BuddyOperator._dominion_init_extended = True


__all__ = ["install_operator_extensions"]
