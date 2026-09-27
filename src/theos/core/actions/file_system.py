from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
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

_PRIVILEGED_READ_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "known_hosts",
        "secrets.json",
    }
)

_PRIVILEGED_READ_SUFFIXES = frozenset(
    {
        ".key",
        ".p12",
        ".pfx",
        ".pem",
    }
)

_PRIVILEGED_WRITE_SUFFIXES = _CONFIRM_OPEN_SUFFIXES | _PRIVILEGED_READ_SUFFIXES

_EXPECTED_PATH = "_theos_expected_path"
_EXPECTED_EXISTS = "_theos_expected_exists"
_EXPECTED_BEFORE_SHA256 = "_theos_expected_before_sha256"
_EXPECTED_CONTENT_SHA256 = "_theos_expected_content_sha256"


def _is_sensitive_path(raw_path: str) -> bool:
    path = Path(raw_path)
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    return (
        name in _PRIVILEGED_READ_NAMES
        or name.startswith(".env.")
        or suffix in _PRIVILEGED_WRITE_SUFFIXES
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
                message="O caminho está vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.inspect(raw_path)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar esse caminho.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_INSPECTION_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não encontrei o caminho {raw_path}.",
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
                message="A pasta raiz e o termo de busca são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.find(raw_root, query)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui pesquisar nesse caminho.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_SEARCH_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não encontrei a pasta raiz {raw_root}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        if not bool(evidence.get("is_directory")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"O caminho raiz não é uma pasta: {raw_root}.",
                evidence=evidence,
                error_code="PATH_NOT_DIRECTORY",
            )

        matches = evidence.get("matches", [])
        count = len(matches) if isinstance(matches, list) else 0
        if count == 0:
            message = f"Pesquisa concluída: nenhum resultado para {query}."
        else:
            message = f"Pesquisa concluída: {count} resultado(s) para {query}."

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
                message="O caminho está vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.open_path(raw_path)
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O Windows não aceitou a solicitação de abertura.",
                evidence={"exception": type(exc).__name__},
                error_code="PATH_OPEN_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não encontrei o caminho {raw_path}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        resolved = Path(str(evidence["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"Solicitação de abertura enviada ao Windows para {resolved.name or resolved}.",
            evidence=evidence,
        )


class ReadTextFileAction:
    name = "read_text_file"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        path = Path(raw_path)
        name = path.name.casefold()
        suffix = path.suffix.casefold()
        if (
            name in _PRIVILEGED_READ_NAMES
            or name.startswith(".env.")
            or suffix in _PRIVILEGED_READ_SUFFIXES
        ):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O caminho está vazio.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.read_text(raw_path)
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ler esse arquivo.",
                evidence={"exception": type(exc).__name__},
                error_code="FILE_READ_FAILED",
            )

        if not bool(evidence.get("exists")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"Não encontrei o arquivo {raw_path}.",
                evidence=evidence,
                error_code="PATH_NOT_FOUND",
            )

        if not bool(evidence.get("is_file")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"O caminho não é um arquivo: {raw_path}.",
                evidence=evidence,
                error_code="PATH_NOT_FILE",
            )

        if not bool(evidence.get("text")):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O arquivo não parece ser texto compatível com a leitura controlada.",
                evidence=evidence,
                error_code="FILE_NOT_TEXT",
            )

        resolved = Path(str(evidence["path"]))
        suffix = " (leitura parcial)" if bool(evidence.get("truncated")) else ""
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"Arquivo lido: {resolved.name or resolved}{suffix}.",
            evidence=evidence,
        )


class WriteTextFileAction:
    name = "write_text_file"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        if _is_sensitive_path(raw_path):
            return ActionRisk.PRIVILEGED

        try:
            exists = self._windows.resolve(raw_path).exists()
        except OSError:
            return ActionRisk.DESTRUCTIVE
        return ActionRisk.DESTRUCTIVE if exists else ActionRisk.CONFIRM

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        content = request.arguments.get("content")
        if not raw_path or not isinstance(content, str):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: argumentos inválidos.",
            )

        try:
            evidence = self._windows.preview_text_write(raw_path, content)
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            reason = str(evidence.get("error", "WRITE_PREVIEW_REJECTED"))
            return ConfirmationPreview(
                allowed=False,
                text=f"Escrita bloqueada antes da confirmação: {reason}.",
            )

        mode = (
            "CRIAR NOVO ARQUIVO"
            if evidence["mode"] == "create"
            else "SUBSTITUIR ARQUIVO"
        )
        path = str(evidence["path"])
        if _is_sensitive_path(raw_path):
            preview_text = (
                f"{mode}\n"
                f"Caminho: {path}\n"
                "Prévia de conteúdo ocultada por ser um caminho sensível.\n"
                f"Novo tamanho: {evidence['new_bytes']} byte(s).\n"
                f"Novo SHA-256: {evidence['new_sha256']}"
            )
        else:
            diff = str(evidence.get("diff", ""))
            if not diff:
                diff = "(nenhuma diferença textual; o conteúdo já é equivalente)"
            preview_text = f"{mode}\nCaminho: {path}\n\n{diff}"

        return ConfirmationPreview(
            allowed=True,
            text=preview_text,
            execution_guard={
                _EXPECTED_PATH: path,
                _EXPECTED_EXISTS: bool(evidence["exists"]),
                _EXPECTED_BEFORE_SHA256: evidence.get("before_sha256"),
                _EXPECTED_CONTENT_SHA256: str(evidence["new_sha256"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        content = request.arguments.get("content")
        if not raw_path or not isinstance(content, str):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O caminho e o conteúdo textual são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        expected_path = request.arguments.get(_EXPECTED_PATH)
        expected_exists = request.arguments.get(_EXPECTED_EXISTS)
        expected_before_sha256 = request.arguments.get(_EXPECTED_BEFORE_SHA256)
        expected_content_sha256 = request.arguments.get(_EXPECTED_CONTENT_SHA256)
        if (
            not isinstance(expected_path, str)
            or not isinstance(expected_exists, bool)
            or (
                expected_before_sha256 is not None
                and not isinstance(expected_before_sha256, str)
            )
            or not isinstance(expected_content_sha256, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A escrita não possui uma prévia local aprovada.",
                error_code="WRITE_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.write_text(
                raw_path,
                content,
                expected_path=expected_path,
                expected_exists=expected_exists,
                expected_before_sha256=expected_before_sha256,
                expected_content_sha256=expected_content_sha256,
            )
        except RuntimeError as exc:
            code = str(exc)
            if code in {"WRITE_TARGET_CHANGED", "WRITE_CONTENT_CHANGED"}:
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O arquivo ou conteúdo mudou depois da prévia; "
                        "a escrita foi bloqueada."
                    ),
                    evidence={"reason": code},
                    error_code="FILE_CHANGED_AFTER_PREVIEW",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A verificação da escrita falhou.",
                evidence={"reason": code},
                error_code="FILE_WRITE_VERIFICATION_FAILED",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui gravar esse arquivo.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="FILE_WRITE_FAILED",
            )

        resolved = Path(str(evidence["path"]))
        if not bool(evidence.get("written")):
            message = f"Nenhuma alteração necessária em {resolved.name or resolved}."
        elif bool(evidence.get("existed_before")):
            message = f"Arquivo atualizado: {resolved.name or resolved}."
        else:
            message = f"Arquivo criado: {resolved.name or resolved}."

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )
