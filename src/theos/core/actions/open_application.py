from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.core.applications.registry import ApplicationRegistry
from theos.integrations.windows.applications import WindowsApplicationAdapter


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