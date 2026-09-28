from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.open_application import OpenApplicationAction


def _request(application: str) -> ActionRequest:
    return ActionRequest(
        action="open_application",
        arguments={"application": application},
    )


def test_natural_notepad_phrase_stays_normal_risk() -> None:
    assert (
        OpenApplicationAction.risk_for(_request("um bloco de notas"))
        is ActionRisk.NORMAL
    )


def test_natural_powershell_phrase_cannot_bypass_confirmation() -> None:
    assert (
        OpenApplicationAction.risk_for(_request("um PowerShell"))
        is ActionRisk.CONFIRM
    )
    assert (
        OpenApplicationAction.risk_for(_request("o prompt de comando"))
        is ActionRisk.CONFIRM
    )


def test_article_only_does_not_become_another_application() -> None:
    assert OpenApplicationAction.risk_for(_request("um")) is ActionRisk.NORMAL
