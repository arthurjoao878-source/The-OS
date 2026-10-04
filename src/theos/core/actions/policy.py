"""Temporary local approval bridge.

M95R keeps the existing confirmation behavior to avoid regressions while the canonical
authority boundary belongs to the separate Phoenix layer. This module must not grow
into Phoenix policy infrastructure inside The Hands.
"""

from __future__ import annotations

from theos.core.actions.contracts import ActionRisk

LEGACY_LOCAL_APPROVAL_BRIDGE = True

_CONFIRMATION_RISKS = frozenset(
    {
        ActionRisk.CONFIRM,
        ActionRisk.DESTRUCTIVE,
        ActionRisk.PRIVILEGED,
    }
)


def requires_confirmation(risk: ActionRisk) -> bool:
    return risk in _CONFIRMATION_RISKS
