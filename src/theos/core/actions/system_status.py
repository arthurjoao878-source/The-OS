from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.integrations.windows.system_status import WindowsSystemStatusAdapter


class SystemStatusAction:
    name = "system_status"
    risk = ActionRisk.READ_ONLY

    def __init__(self, windows: WindowsSystemStatusAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        try:
            evidence = self._windows.snapshot()
        except (OSError, RuntimeError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui coletar o status do sistema.",
                evidence={"exception": type(exc).__name__},
                error_code="SYSTEM_STATUS_FAILED",
            )

        cpu = float(evidence["cpu_percent"])
        memory = float(evidence["memory_percent"])
        disk = float(evidence["disk_percent"])

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                "Status do sistema coletado: "
                f"CPU {cpu:.1f}%, memória {memory:.1f}%, disco {disk:.1f}%."
            ),
            evidence=evidence,
        )
