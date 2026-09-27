from __future__ import annotations

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter


class WindowSnapshotAction:
    name = "window_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        _ = request
        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR JANELAS VISÍVEIS\n"
                "A LYRA enumerará localmente janelas de nível superior que estão visíveis "
                "e enviará ao provedor de IA somente título da janela, nome do processo "
                "e PID.\n"
                "Limite de saída: 12 janelas; títulos são limitados a 160 caracteres.\n"
                "Não serão coletados conteúdo interno das janelas, teclas digitadas, "
                "capturas de tela, caminhos de executáveis ou títulos de janelas ocultas."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        _ = request
        try:
            evidence = self._windows.snapshot()
        except (OSError, RuntimeError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar as janelas visíveis.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_SNAPSHOT_FAILED",
            )

        observed = int(evidence["observed_windows"])
        returned = int(evidence["returned_windows"])
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janelas inspecionadas: {observed} visíveis com título; "
                f"{returned} retornadas."
            ),
            evidence=evidence,
        )
