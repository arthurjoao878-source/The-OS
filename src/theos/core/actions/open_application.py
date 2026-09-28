from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.applications.registry import (
    ApplicationRegistry,
    normalize_application_name,
)
from theos.integrations.windows.applications import WindowsApplicationAdapter

_CONFIRM_REQUIRED_APPLICATIONS = frozenset(
    {
        "cmd",
        "cmd.exe",
        "command prompt",
        "editor do registro",
        "powershell",
        "powershell.exe",
        "prompt de comando",
        "pwsh",
        "pwsh.exe",
        "regedit",
        "regedit.exe",
        "terminal",
        "windows powershell",
        "windows terminal",
        "wt",
        "wt.exe",
    }
)


class OpenApplicationAction:
    name = "open_application"
    risk = ActionRisk.NORMAL

    def __init__(
        self,
        applications: ApplicationRegistry,
        windows: WindowsApplicationAdapter,
    ) -> None:
        self._applications = applications
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_name = str(request.arguments.get("application", ""))
        normalized_name = normalize_application_name(raw_name).casefold()
        if normalized_name in _CONFIRM_REQUIRED_APPLICATIONS:
            return ActionRisk.CONFIRM
        return ActionRisk.NORMAL

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_name = str(request.arguments.get("application", "")).strip()
        if not raw_name:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O nome do aplicativo está vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        app = self._applications.resolve(raw_name)
        if app is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não encontrei {raw_name}.",
                error_code="APPLICATION_NOT_FOUND",
            )

        try:
            launch_pid = self._windows.launch(app)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não consegui abrir {app.name}.",
                evidence={"exception": type(exc).__name__},
                error_code="ACTION_EXECUTION_FAILED",
            )

        evidence = self._windows.verify_running(app)
        evidence["launch_pid"] = launch_pid
        evidence["resolved_target"] = app.target

        if not bool(evidence.get("verified")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Tentei abrir {app.name}, mas não consegui verificar a execução.",
                evidence=evidence,
                error_code="ACTION_VERIFICATION_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"{app.name} aberto.",
            evidence=evidence,
        )
