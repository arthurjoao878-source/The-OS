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

class ActivateWindowAction:
    name = "activate_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="PID e título exatos da janela são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.activate_window(pid, title.strip())
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Há mais de uma janela visível com esse mesmo PID e título; "
                        "a ativação foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_FOREGROUND_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou essa janela em primeiro plano.",
                    evidence={"reason": reason},
                    error_code="WINDOW_ACTIVATION_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ativar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_ACTIVATION_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ativar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_ACTIVATION_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela ativada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']})."
            ),
            evidence=evidence,
        )
