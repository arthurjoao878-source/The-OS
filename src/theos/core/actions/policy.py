from __future__ import annotations

from theos.core.actions.contracts import ActionRisk

_CONFIRMATION_RISKS = frozenset(
    {
        ActionRisk.CONFIRM,
        ActionRisk.DESTRUCTIVE,
        ActionRisk.PRIVILEGED,
    }
)


def requires_confirmation(risk: ActionRisk) -> bool:
    return risk in _CONFIRMATION_RISKS
