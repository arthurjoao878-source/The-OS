from __future__ import annotations

import hashlib
from pathlib import Path

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.file_system import (
    MAX_TEXT_SEARCH_BYTES_PER_FILE,
    MAX_TEXT_SEARCH_DEPTH,
    MAX_TEXT_SEARCH_FILES,
    MAX_TEXT_SEARCH_RESULTS,
    MAX_TEXT_SEARCH_SNIPPET_CHARS,
    MAX_TEXT_SEARCH_TOTAL_BYTES,
    WindowsFileSystemAdapter,
)

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
_EXPECTED_MUTATION_PATH = "_theos_expected_mutation_path"
_EXPECTED_MUTATION_PARENT = "_theos_expected_mutation_parent"
_EXPECTED_SOURCE = "_theos_expected_source"
_EXPECTED_DESTINATION = "_theos_expected_destination"
_EXPECTED_SOURCE_SIGNATURE = "_theos_expected_source_signature"
_EXPECTED_COPY_MANIFEST_SHA256 = "_theos_expected_copy_manifest_sha256"
_EXPECTED_OLD_TEXT_SHA256 = "_theos_expected_old_text_sha256"
_EXPECTED_NEW_TEXT_SHA256 = "_theos_expected_new_text_sha256"
_EXPECTED_OLD_BLOCK_SHA256 = "_theos_expected_old_block_sha256"
_EXPECTED_NEW_BLOCK_SHA256 = "_theos_expected_new_block_sha256"


def _is_privileged_read_path(raw_path: str) -> bool:
    path = Path(raw_path)
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    return (
        name in _PRIVILEGED_READ_NAMES
        or name.startswith(".env.")
        or suffix in _PRIVILEGED_READ_SUFFIXES
    )


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


class SearchTextAction:
    name = "search_text"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_root = str(request.arguments.get("root", "")).strip()
        query = str(request.arguments.get("query", "")).strip()
        if not raw_root or not query:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: raiz ou texto de busca vazio.",
            )

        return ConfirmationPreview(
            allowed=True,
            text=(
                "PESQUISAR TEXTO EM ARQUIVOS\n"
                f"Raiz: {raw_root}\n"
                f"Texto literal: {query}\n"
                "A busca só começará após esta confirmação. Ela é literal e "
                "case-insensitive, não usa regex/fuzzy, não segue links/junctions "
                "e pula caminhos conhecidos como credenciais/chaves.\n"
                f"Limites: profundidade {MAX_TEXT_SEARCH_DEPTH}; "
                f"{MAX_TEXT_SEARCH_FILES} arquivos; "
                f"{MAX_TEXT_SEARCH_BYTES_PER_FILE} byte(s) por arquivo; "
                f"{MAX_TEXT_SEARCH_TOTAL_BYTES} byte(s) no total; "
                f"{MAX_TEXT_SEARCH_RESULTS} resultados; "
                f"trechos de até {MAX_TEXT_SEARCH_SNIPPET_CHARS} caracteres."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_root = str(request.arguments.get("root", "")).strip()
        query = str(request.arguments.get("query", "")).strip()
        if not raw_root or not query:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A pasta raiz e o texto de busca são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.search_text(
                raw_root,
                query,
                should_skip=lambda path: _is_privileged_read_path(str(path)),
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui pesquisar texto nessa pasta.",
                evidence={"exception": type(exc).__name__},
                error_code="TEXT_SEARCH_FAILED",
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
        complete = bool(evidence.get("complete"))
        qualifier = "Busca concluída" if complete else "Busca parcial concluída"
        if count:
            message = f"{qualifier}: {count} ocorrência(s) para {query}."
        else:
            message = f"{qualifier}: nenhuma ocorrência para {query}."

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
        if _is_privileged_read_path(raw_path):
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


class ReadTextLinesAction:
    name = "read_text_lines"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        if _is_privileged_read_path(raw_path):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        start_line = request.arguments.get("start_line")
        max_lines = request.arguments.get("max_lines")
        if (
            not raw_path
            or not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(max_lines, int)
            or isinstance(max_lines, bool)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Caminho, linha inicial e quantidade de linhas são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.read_text_lines(
                raw_path,
                start_line,
                max_lines,
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ler esse intervalo de linhas.",
                evidence={"exception": type(exc).__name__},
                error_code="TEXT_LINE_READ_FAILED",
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
        if not bool(evidence.get("start_line_reached")):
            if bool(evidence.get("scan_truncated")):
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "A linha inicial não foi alcançada dentro do limite local "
                        "de varredura; não posso afirmar que ela não existe."
                    ),
                    evidence=evidence,
                    error_code="TEXT_LINE_RANGE_BEYOND_SCAN_LIMIT",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=f"A linha inicial {start_line} não existe nesse arquivo.",
                evidence=evidence,
                error_code="TEXT_LINE_START_NOT_FOUND",
            )

        resolved = Path(str(evidence["path"]))
        suffix = " (trecho parcial)" if not bool(evidence.get("range_complete")) else ""
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Linhas a partir de {start_line} lidas de "
                f"{resolved.name or resolved}{suffix}."
            ),
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
class ReplaceTextLiteralAction:
    name = "replace_text_literal"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        try:
            protected = self._windows.is_protected_system_path(raw_path)
        except OSError:
            return ActionRisk.PRIVILEGED
        if _is_sensitive_path(raw_path) or protected:
            return ActionRisk.PRIVILEGED
        return ActionRisk.DESTRUCTIVE

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        old_text = request.arguments.get("old_text")
        new_text = request.arguments.get("new_text")
        if (
            not raw_path
            or not isinstance(old_text, str)
            or not isinstance(new_text, str)
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: argumentos inválidos.",
            )

        try:
            evidence = self._windows.preview_literal_text_replace(
                raw_path,
                old_text,
                new_text,
            )
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            reason = str(
                evidence.get("error", "LITERAL_REPLACE_PREVIEW_REJECTED")
            )
            count = evidence.get("match_count")
            suffix = (
                f" Ocorrências encontradas: {count}."
                if isinstance(count, int)
                else ""
            )
            return ConfirmationPreview(
                allowed=False,
                text=f"Substituição bloqueada antes da confirmação: {reason}.{suffix}",
            )

        path = str(evidence["path"])
        if _is_privileged_read_path(raw_path):
            preview_text = (
                "SUBSTITUIR TEXTO LITERAL\n"
                f"Caminho: {path}\n"
                "Prévia textual ocultada por ser um caminho de credencial/chave.\n"
                "Ocorrência literal única verificada localmente.\n"
                f"SHA-256 atual: {evidence['before_sha256']}\n"
                f"SHA-256 resultante: {evidence['after_sha256']}"
            )
        else:
            diff = str(evidence.get("diff", ""))
            preview_text = (
                "SUBSTITUIR TEXTO LITERAL\n"
                f"Caminho: {path}\n"
                "Ocorrência literal única verificada localmente.\n\n"
                f"{diff}"
            )

        return ConfirmationPreview(
            allowed=True,
            text=preview_text,
            execution_guard={
                _EXPECTED_PATH: path,
                _EXPECTED_BEFORE_SHA256: str(evidence["before_sha256"]),
                _EXPECTED_CONTENT_SHA256: str(evidence["after_sha256"]),
                _EXPECTED_OLD_TEXT_SHA256: str(evidence["old_text_sha256"]),
                _EXPECTED_NEW_TEXT_SHA256: str(evidence["new_text_sha256"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        old_text = request.arguments.get("old_text")
        new_text = request.arguments.get("new_text")
        if (
            not raw_path
            or not isinstance(old_text, str)
            or not isinstance(new_text, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Caminho, texto antigo e texto novo são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        expected_path = request.arguments.get(_EXPECTED_PATH)
        expected_before_sha256 = request.arguments.get(_EXPECTED_BEFORE_SHA256)
        expected_after_sha256 = request.arguments.get(_EXPECTED_CONTENT_SHA256)
        expected_old_sha256 = request.arguments.get(_EXPECTED_OLD_TEXT_SHA256)
        expected_new_sha256 = request.arguments.get(_EXPECTED_NEW_TEXT_SHA256)
        guarded = (
            expected_path,
            expected_before_sha256,
            expected_after_sha256,
            expected_old_sha256,
            expected_new_sha256,
        )
        if not all(isinstance(value, str) for value in guarded):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A substituição não possui uma prévia local aprovada.",
                error_code="LITERAL_REPLACE_PREVIEW_REQUIRED",
            )

        if (
            hashlib.sha256(old_text.encode("utf-8")).hexdigest()
            != expected_old_sha256
            or hashlib.sha256(new_text.encode("utf-8")).hexdigest()
            != expected_new_sha256
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O texto proposto mudou depois da prévia; a ação foi bloqueada.",
                error_code="REPLACEMENT_CHANGED_AFTER_PREVIEW",
            )

        try:
            evidence = self._windows.replace_text_literal(
                raw_path,
                old_text,
                new_text,
                expected_path=expected_path,
                expected_before_sha256=expected_before_sha256,
                expected_after_sha256=expected_after_sha256,
            )
        except RuntimeError as exc:
            code = str(exc)
            if code in {
                "LITERAL_REPLACE_TARGET_CHANGED",
                "LITERAL_REPLACE_CONTENT_CHANGED",
            }:
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O arquivo ou o resultado proposto mudou depois da prévia; "
                        "a substituição foi bloqueada."
                    ),
                    evidence={"reason": code},
                    error_code="FILE_CHANGED_AFTER_PREVIEW",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A verificação da substituição textual falhou.",
                evidence={"reason": code},
                error_code="LITERAL_REPLACE_VERIFICATION_FAILED",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar a substituição textual.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="LITERAL_REPLACE_FAILED",
            )

        resolved = Path(str(evidence["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"Substituição textual verificada em {resolved.name or resolved}.",
            evidence=evidence,
        )


class ReplaceTextBlockAction:
    name = "replace_text_block"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        try:
            protected = self._windows.is_protected_system_path(raw_path)
        except OSError:
            return ActionRisk.PRIVILEGED
        if _is_sensitive_path(raw_path) or protected:
            return ActionRisk.PRIVILEGED
        return ActionRisk.DESTRUCTIVE

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        old_block = request.arguments.get("old_block")
        new_block = request.arguments.get("new_block")
        if (
            not raw_path
            or not isinstance(old_block, str)
            or not isinstance(new_block, str)
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: argumentos inválidos.",
            )

        try:
            evidence = self._windows.preview_literal_block_replace(
                raw_path,
                old_block,
                new_block,
            )
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            reason = str(
                evidence.get("error", "LITERAL_BLOCK_PREVIEW_REJECTED")
            )
            count = evidence.get("match_count")
            suffix = (
                f" Ocorrências encontradas: {count}."
                if isinstance(count, int)
                else ""
            )
            return ConfirmationPreview(
                allowed=False,
                text=f"Substituição bloqueada antes da confirmação: {reason}.{suffix}",
            )

        path = str(evidence["path"])
        if _is_privileged_read_path(raw_path):
            preview_text = (
                "SUBSTITUIR BLOCO LITERAL\n"
                f"Caminho: {path}\n"
                "Prévia textual ocultada por ser um caminho de credencial/chave.\n"
                "Bloco literal único verificado localmente.\n"
                f"Linhas antigas: {evidence['old_block_lines']}\n"
                f"Linhas novas: {evidence['new_block_lines']}\n"
                f"SHA-256 atual: {evidence['before_sha256']}\n"
                f"SHA-256 resultante: {evidence['after_sha256']}"
            )
        else:
            diff = str(evidence.get("diff", ""))
            preview_text = (
                "SUBSTITUIR BLOCO LITERAL\n"
                f"Caminho: {path}\n"
                "Bloco literal único verificado localmente.\n"
                f"Newline aplicado ao bloco novo: {evidence['newline_style']}\n\n"
                f"{diff}"
            )

        return ConfirmationPreview(
            allowed=True,
            text=preview_text,
            execution_guard={
                _EXPECTED_PATH: path,
                _EXPECTED_BEFORE_SHA256: str(evidence["before_sha256"]),
                _EXPECTED_CONTENT_SHA256: str(evidence["after_sha256"]),
                _EXPECTED_OLD_BLOCK_SHA256: str(evidence["old_block_sha256"]),
                _EXPECTED_NEW_BLOCK_SHA256: str(evidence["new_block_sha256"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        old_block = request.arguments.get("old_block")
        new_block = request.arguments.get("new_block")
        if (
            not raw_path
            or not isinstance(old_block, str)
            or not isinstance(new_block, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Caminho, bloco antigo e bloco novo são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        expected_path = request.arguments.get(_EXPECTED_PATH)
        expected_before_sha256 = request.arguments.get(_EXPECTED_BEFORE_SHA256)
        expected_after_sha256 = request.arguments.get(_EXPECTED_CONTENT_SHA256)
        expected_old_sha256 = request.arguments.get(_EXPECTED_OLD_BLOCK_SHA256)
        expected_new_sha256 = request.arguments.get(_EXPECTED_NEW_BLOCK_SHA256)
        guarded = (
            expected_path,
            expected_before_sha256,
            expected_after_sha256,
            expected_old_sha256,
            expected_new_sha256,
        )
        if not all(isinstance(value, str) for value in guarded):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A substituição não possui uma prévia local aprovada.",
                error_code="LITERAL_BLOCK_PREVIEW_REQUIRED",
            )

        if (
            hashlib.sha256(old_block.encode("utf-8")).hexdigest()
            != expected_old_sha256
            or hashlib.sha256(new_block.encode("utf-8")).hexdigest()
            != expected_new_sha256
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O bloco proposto mudou depois da prévia; a ação foi bloqueada.",
                error_code="BLOCK_CHANGED_AFTER_PREVIEW",
            )

        try:
            evidence = self._windows.replace_text_block(
                raw_path,
                old_block,
                new_block,
                expected_path=expected_path,
                expected_before_sha256=expected_before_sha256,
                expected_after_sha256=expected_after_sha256,
            )
        except RuntimeError as exc:
            code = str(exc)
            if code in {
                "LITERAL_BLOCK_TARGET_CHANGED",
                "LITERAL_BLOCK_CONTENT_CHANGED",
            }:
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O arquivo ou o resultado proposto mudou depois da prévia; "
                        "a substituição foi bloqueada."
                    ),
                    evidence={"reason": code},
                    error_code="FILE_CHANGED_AFTER_PREVIEW",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A verificação da substituição do bloco falhou.",
                evidence={"reason": code},
                error_code="LITERAL_BLOCK_VERIFICATION_FAILED",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar a substituição do bloco.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="LITERAL_BLOCK_REPLACE_FAILED",
            )

        resolved = Path(str(evidence["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"Substituição de bloco verificada em {resolved.name or resolved}.",
            evidence=evidence,
        )


class CreateDirectoryAction:
    name = "create_directory"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        if _is_sensitive_path(raw_path) or self._windows.is_protected_system_path(
            raw_path
        ):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho vazio.",
            )

        try:
            evidence = self._windows.preview_create_directory(raw_path)
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Criação de pasta bloqueada antes da confirmação: "
                    f"{evidence.get('error', 'CREATE_DIRECTORY_REJECTED')}."
                ),
            )

        path = str(evidence["path"])
        return ConfirmationPreview(
            allowed=True,
            text=f"CRIAR PASTA\nCaminho: {path}",
            execution_guard={
                _EXPECTED_MUTATION_PATH: path,
                _EXPECTED_MUTATION_PARENT: str(evidence["parent"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        expected_path = request.arguments.get(_EXPECTED_MUTATION_PATH)
        expected_parent = request.arguments.get(_EXPECTED_MUTATION_PARENT)
        if (
            not raw_path
            or not isinstance(expected_path, str)
            or not isinstance(expected_parent, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A criação da pasta não possui uma prévia local aprovada.",
                error_code="MUTATION_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.create_directory(
                raw_path,
                expected_path=expected_path,
                expected_parent=expected_parent,
            )
        except RuntimeError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O destino mudou depois da prévia; a criação foi bloqueada.",
                evidence={"reason": str(exc)},
                error_code="MUTATION_CHANGED_AFTER_PREVIEW",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui criar essa pasta.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="DIRECTORY_CREATE_FAILED",
            )

        resolved = Path(str(evidence["path"]))
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"Pasta criada: {resolved.name or resolved}.",
            evidence=evidence,
        )


class CopyPathAction:
    name = "copy_path"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        if (
            _is_sensitive_path(source)
            or _is_sensitive_path(destination)
            or self._windows.is_protected_system_path(source)
            or self._windows.is_protected_system_path(destination)
        ):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        if not source or not destination:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: origem ou destino vazio.",
            )

        try:
            evidence = self._windows.preview_copy_path(source, destination)
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Cópia bloqueada antes da confirmação: "
                    f"{evidence.get('error', 'COPY_REJECTED')}."
                ),
            )

        kind = "PASTA" if evidence["source_kind"] == "directory" else "ARQUIVO"
        preview_text = (
            f"COPIAR {kind}\n"
            f"Origem: {evidence['source']}\n"
            f"Destino: {evidence['destination']}\n"
            f"Arquivos: {evidence['files']}\n"
            f"Pastas internas: {evidence['directories']}\n"
            f"Tamanho total: {evidence['total_bytes']} byte(s)\n"
            "A origem será preservada e o destino existente nunca será sobrescrito."
        )
        return ConfirmationPreview(
            allowed=True,
            text=preview_text,
            execution_guard={
                _EXPECTED_SOURCE: str(evidence["source"]),
                _EXPECTED_DESTINATION: str(evidence["destination"]),
                _EXPECTED_COPY_MANIFEST_SHA256: str(
                    evidence["source_manifest_sha256"]
                ),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        expected_source = request.arguments.get(_EXPECTED_SOURCE)
        expected_destination = request.arguments.get(_EXPECTED_DESTINATION)
        expected_manifest = request.arguments.get(_EXPECTED_COPY_MANIFEST_SHA256)
        if (
            not source
            or not destination
            or not isinstance(expected_source, str)
            or not isinstance(expected_destination, str)
            or not isinstance(expected_manifest, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A cópia não possui uma prévia local aprovada.",
                error_code="MUTATION_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.copy_path(
                source,
                destination,
                expected_source=expected_source,
                expected_destination=expected_destination,
                expected_source_manifest_sha256=expected_manifest,
            )
        except RuntimeError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A origem ou o destino mudou, ou a verificação da cópia falhou; "
                    "a publicação do destino foi bloqueada."
                ),
                evidence={"reason": str(exc)},
                error_code="COPY_CHANGED_OR_VERIFICATION_FAILED",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui copiar esse caminho.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="PATH_COPY_FAILED",
            )

        destination_path = Path(str(evidence["destination"]))
        if evidence.get("kind") == "directory":
            message = f"Pasta copiada para {destination_path}."
        else:
            message = f"Arquivo copiado para {destination_path}."
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )

class MovePathAction:
    name = "move_path"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        if (
            _is_sensitive_path(source)
            or _is_sensitive_path(destination)
            or self._windows.is_protected_system_path(source)
            or self._windows.is_protected_system_path(destination)
        ):
            return ActionRisk.PRIVILEGED
        return ActionRisk.DESTRUCTIVE

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        if not source or not destination:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: origem ou destino vazio.",
            )

        try:
            evidence = self._windows.preview_move_path(source, destination)
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Movimentação bloqueada antes da confirmação: "
                    f"{evidence.get('error', 'MOVE_REJECTED')}."
                ),
            )

        return ConfirmationPreview(
            allowed=True,
            text=(
                "MOVER/RENOMEAR CAMINHO\n"
                f"Origem: {evidence['source']}\n"
                f"Destino: {evidence['destination']}\n"
                "O destino existente nunca será sobrescrito."
            ),
            execution_guard={
                _EXPECTED_SOURCE: str(evidence["source"]),
                _EXPECTED_DESTINATION: str(evidence["destination"]),
                _EXPECTED_SOURCE_SIGNATURE: str(evidence["source_signature"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        source = str(request.arguments.get("source", "")).strip()
        destination = str(request.arguments.get("destination", "")).strip()
        expected_source = request.arguments.get(_EXPECTED_SOURCE)
        expected_destination = request.arguments.get(_EXPECTED_DESTINATION)
        expected_signature = request.arguments.get(_EXPECTED_SOURCE_SIGNATURE)
        if (
            not source
            or not destination
            or not isinstance(expected_source, str)
            or not isinstance(expected_destination, str)
            or not isinstance(expected_signature, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A movimentação não possui uma prévia local aprovada.",
                error_code="MUTATION_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.move_path(
                source,
                destination,
                expected_source=expected_source,
                expected_destination=expected_destination,
                expected_source_signature=expected_signature,
            )
        except RuntimeError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A origem ou o destino mudou depois da prévia; "
                    "a movimentação foi bloqueada."
                ),
                evidence={"reason": str(exc)},
                error_code="MUTATION_CHANGED_AFTER_PREVIEW",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui mover ou renomear esse caminho.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="PATH_MOVE_FAILED",
            )

        destination_path = Path(str(evidence["destination"]))
        noun = "Pasta" if evidence.get("kind") == "directory" else "Arquivo"
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"{noun} movido para {destination_path}.",
            evidence=evidence,
        )


class TrashPathAction:
    name = "trash_path"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsFileSystemAdapter) -> None:
        self._windows = windows

    def risk_for(self, request: ActionRequest) -> ActionRisk:
        raw_path = str(request.arguments.get("path", "")).strip()
        if _is_sensitive_path(raw_path) or self._windows.is_protected_system_path(
            raw_path
        ):
            return ActionRisk.PRIVILEGED
        return ActionRisk.DESTRUCTIVE

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho vazio.",
            )

        try:
            evidence = self._windows.preview_trash_path(raw_path)
        except OSError as exc:
            return ConfirmationPreview(
                allowed=False,
                text=f"Não foi possível preparar a prévia ({type(exc).__name__}).",
            )

        if not bool(evidence.get("allowed")):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Envio para a Lixeira bloqueado antes da confirmação: "
                    f"{evidence.get('error', 'TRASH_REJECTED')}."
                ),
            )

        return ConfirmationPreview(
            allowed=True,
            text=(
                "ENVIAR PARA A LIXEIRA DO WINDOWS\n"
                f"Caminho: {evidence['path']}\n"
                f"Tipo: {evidence['kind']}\n"
                "A ação não usa exclusão permanente."
            ),
            execution_guard={
                _EXPECTED_MUTATION_PATH: str(evidence["path"]),
                _EXPECTED_SOURCE_SIGNATURE: str(evidence["source_signature"]),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        expected_path = request.arguments.get(_EXPECTED_MUTATION_PATH)
        expected_signature = request.arguments.get(_EXPECTED_SOURCE_SIGNATURE)
        if (
            not raw_path
            or not isinstance(expected_path, str)
            or not isinstance(expected_signature, str)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O envio para a Lixeira não possui uma prévia local aprovada.",
                error_code="MUTATION_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.trash_path(
                raw_path,
                expected_path=expected_path,
                expected_source_signature=expected_signature,
            )
        except RuntimeError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "O caminho mudou ou a Lixeira recusou a operação; "
                    "nenhuma conclusão de sucesso foi emitida."
                ),
                evidence={"reason": str(exc)},
                error_code="TRASH_OPERATION_FAILED",
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar esse caminho para a Lixeira.",
                evidence={"exception": type(exc).__name__, "reason": str(exc)},
                error_code="TRASH_OPERATION_FAILED",
            )

        resolved = Path(str(evidence["path"]))
        noun = "Pasta" if evidence.get("kind") == "directory" else "Arquivo"
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=f"{noun} enviado para a Lixeira: {resolved.name or resolved}.",
            evidence=evidence,
        )
