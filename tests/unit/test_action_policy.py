from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.open_application import OpenApplicationAction
from theos.core.actions.policy import requires_confirmation


def test_sensitive_risks_require_confirmation() -> None:
    assert requires_confirmation(ActionRisk.READ_ONLY) is False
    assert requires_confirmation(ActionRisk.NORMAL) is False
    assert requires_confirmation(ActionRisk.CONFIRM) is True
    assert requires_confirmation(ActionRisk.DESTRUCTIVE) is True
    assert requires_confirmation(ActionRisk.PRIVILEGED) is True


def test_open_application_marks_shells_for_confirmation() -> None:
    assert OpenApplicationAction.risk_for(
        ActionRequest(
            action="open_application",
            arguments={"application": "PowerShell"},
        )
    ) is ActionRisk.CONFIRM

    assert OpenApplicationAction.risk_for(
        ActionRequest(
            action="open_application",
            arguments={"application": "Bloco de Notas"},
        )
    ) is ActionRisk.NORMAL
