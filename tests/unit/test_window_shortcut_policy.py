from __future__ import annotations

from theos.core.actions.contracts import ActionRisk
from theos.core.keyboard_shortcuts import (
    ALLOWED_WINDOW_SHORTCUTS,
    DESTRUCTIVE_WINDOW_SHORTCUTS,
    PRIVILEGED_WINDOW_SHORTCUTS,
    WINDOW_SHORTCUT_SPECS,
    is_allowed_window_shortcut,
    is_destructive_window_shortcut,
    is_privileged_window_shortcut,
)


def test_window_shortcut_allowlist_is_registry_derived() -> None:
    assert ALLOWED_WINDOW_SHORTCUTS == tuple(
        spec.name for spec in WINDOW_SHORTCUT_SPECS
    )
    assert DESTRUCTIVE_WINDOW_SHORTCUTS == frozenset(
        spec.name
        for spec in WINDOW_SHORTCUT_SPECS
        if spec.risk is ActionRisk.DESTRUCTIVE
    )
    assert PRIVILEGED_WINDOW_SHORTCUTS == frozenset(
        spec.name
        for spec in WINDOW_SHORTCUT_SPECS
        if spec.risk is ActionRisk.PRIVILEGED
    )

    for spec in WINDOW_SHORTCUT_SPECS:
        assert is_allowed_window_shortcut(spec.name) is True
        assert is_destructive_window_shortcut(spec.name) is (
            spec.risk is ActionRisk.DESTRUCTIVE
        )
        assert is_privileged_window_shortcut(spec.name) is (
            spec.risk is ActionRisk.PRIVILEGED
        )

    for invalid in ("ctrl_a", "CTRL_A_EXTRA", "SHIFT_F13", None):
        assert is_allowed_window_shortcut(invalid) is False


def test_window_shortcut_risk_sets_do_not_overlap() -> None:
    assert DESTRUCTIVE_WINDOW_SHORTCUTS.isdisjoint(
        PRIVILEGED_WINDOW_SHORTCUTS
    )
