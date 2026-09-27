from __future__ import annotations

import psutil

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.processes import WindowsProcessAdapter


class ProcessSnapshotAction:
    name = "process_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsProcessAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        _ = request
        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR PROCESSOS\n"
                "A LYRA enumerará localmente os processos em execução e enviará ao "
                "provedor de IA somente nome do processo, PID e memória residente (RSS).\n"
                "Limite de saída: 12 processos, ordenados por memória residente.\n"
                "Não serão coletados caminho do executável, linha de comando, usuário "
                "ou arquivos abertos."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        try:
            evidence = self._windows.snapshot()
        except (OSError, RuntimeError, psutil.Error) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar os processos em execução.",
                evidence={"exception": type(exc).__name__},
                error_code="PROCESS_SNAPSHOT_FAILED",
            )

        observed = int(evidence["observed_processes"])
        returned = int(evidence["returned_processes"])
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Processos inspecionados: {observed} observados; "
                f"{returned} retornados por memória residente."
            ),
            evidence=evidence,
        )
