from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
from theos.integrations.windows.file_system import WindowsFileSystemAdapter

_CONFIRM_OPEN_SUFFIXES = frozenset(
    {
        ".bat",
        ".cmd",
        ".com",
        ".cpl",
        ".exe",
        ".hta",
        ".jar",
        ".js",
        ".jse",
        ".lnk",
        ".msc",
        ".msi",
        ".msp",
        ".ps1",
        ".psd1",
        ".psm1",
        ".py",
        ".pyw",
        ".reg",
        ".scr",
        ".sh",
        ".url",
        ".vbe",
        ".vbs",
        ".wsf",
        ".wsh",
    }
)


class InspectPathAction:
    name = "inspect_path"
    risk = ActionRisk.READ_ONLY

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O caminho estÃ¡ vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.inspect(raw_path)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="NÃ£o consegui inspecionar esse caminho.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_INSPECTION_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"NÃ£o encontrei o caminho {raw_path}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        resolved = Path(str(evidence["path"]))
        kind = evidence.get("kind")
        message = (
            f"Pasta inspecionada: {resolved.name or resolved}."
            if kind == "directory"
            else f"Arquivo inspecionado: {resolved.name or resolved}."
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )


class FindPathAction:
    name = "find_path"
    risk = ActionRisk.READ_ONLY

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_root = str(request.arguments.get("root", "")).strip()
        query = str(request.arguments.get("query", "")).strip()
        if not raw_root or not query:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A pasta raiz e o termo de busca sÃ£o obrigatÃ³rios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.find(raw_root, query)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="NÃ£o consegui pesquisar nesse caminho.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_SEARCH_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"NÃ£o encontrei a pasta raiz {raw_root}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        if not bool(evidence.get("is_directory")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"O caminho raiz nÃ£o Ã© uma pasta: {raw_root}.",
                evidence=evidence,
                error_code="PATH_NOT_DIRECTORY",
            )

        matches = evidence.get("matches", [])
        count = len(matches) if isinstance(matches, list) else 0
        if count == 0:
            message = f"Pesquisa concluÃ­da: nenhum resultado para {query}."
        else:
            message = f"Pesquisa concluÃ­da: {count} resultado(s) para {query}."

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )


class OpenPathAction:
    name = "open_path"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        suffix = Path(raw_path).suffix.casefold()
        if suffix in _CONFIRM_OPEN_SUFFIXES:
            return ActionRisk.CONFIRM
        return ActionRisk.NORMAL

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O caminho estÃ¡ vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.open_path(raw_path)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O Windows nÃ£o aceitou a solicitaÃ§Ã£o de abertura.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_OPEN_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"NÃ£o encontrei o caminho {raw_path}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        resolved = Path(str(evidence["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"SolicitaÃ§Ã£o de abertura enviada ao Windows para {resolved.name or resolved}.",
            evidence=evidence,
        )
