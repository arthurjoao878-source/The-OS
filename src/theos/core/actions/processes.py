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

_EXPECTED_PROCESS_PID = "_theos_expected_process_pid"
_EXPECTED_PROCESS_NAME = "_theos_expected_process_name"
_EXPECTED_PROCESS_CREATE_TIME = "_theos_expected_process_create_time"


class TerminateProcessAction:
    name = "terminate_process"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsProcessAdapter) -> None:
        self._windows = windows

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return ConfirmationPreview(
                allowed=False,
                text="Encerramento bloqueado antes da confirmação: INVALID_PID.",
            )

        try:
            evidence = self._windows.preview_terminate_process(pid)
        except psutil.Error as exc:
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Não foi possível preparar a prévia do processo "
                    f"({type(exc).__name__})."
                ),
            )

        if not bool(evidence.get("allowed")):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Encerramento bloqueado antes da confirmação: "
                    f"{evidence.get('error', 'PROCESS_TERMINATION_BLOCKED')}."
                ),
            )

        name = str(evidence["name"])
        create_time = float(evidence["create_time"])
        return ConfirmationPreview(
            allowed=True,
            text=(
                "ENCERRAR PROCESSO\n"
                f"Processo: {name}\n"
                f"PID: {pid}\n"
                "Atenção: encerrar o processo pode descartar trabalho não salvo.\n"
                "A identidade do processo será revalidada imediatamente antes da ação."
            ),
            execution_guard={
                _EXPECTED_PROCESS_PID: pid,
                _EXPECTED_PROCESS_NAME: name,
                _EXPECTED_PROCESS_CREATE_TIME: create_time,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        expected_pid = request.arguments.get(_EXPECTED_PROCESS_PID)
        expected_name = request.arguments.get(_EXPECTED_PROCESS_NAME)
        expected_create_time = request.arguments.get(_EXPECTED_PROCESS_CREATE_TIME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(expected_pid, int)
            or isinstance(expected_pid, bool)
            or expected_pid != pid
            or not isinstance(expected_name, str)
            or not isinstance(expected_create_time, (int, float))
            or isinstance(expected_create_time, bool)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O encerramento não possui uma prévia local aprovada.",
                error_code="PROCESS_TERMINATION_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.terminate_process(
                pid,
                expected_name=expected_name,
                expected_create_time=float(expected_create_time),
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "PROCESS_IDENTITY_CHANGED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O processo mudou depois da prévia; "
                        "o encerramento foi bloqueado."
                    ),
                    evidence={"reason": reason},
                    error_code="PROCESS_CHANGED_AFTER_PREVIEW",
                )
            if reason in {
                "PROCESS_TERMINATION_TIMEOUT",
                "PROCESS_STILL_RUNNING",
            }:
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não consegui verificar que o processo foi encerrado.",
                    evidence={"reason": reason},
                    error_code="PROCESS_TERMINATION_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O encerramento do processo foi bloqueado.",
                evidence={"reason": reason},
                error_code="PROCESS_TERMINATION_BLOCKED",
            )
        except psutil.Error as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui encerrar esse processo.",
                evidence={"exception": type(exc).__name__},
                error_code="PROCESS_TERMINATION_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Processo encerrado e verificado: {expected_name} (PID {pid})."
            ),
            evidence=evidence,
        )
