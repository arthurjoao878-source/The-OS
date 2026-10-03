from __future__ import annotations

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.file_system import _is_privileged_read_path
from theos.integrations.windows.git_local import (
    MAX_GIT_DIFF_FILE_BYTES,
    MAX_GIT_DIFF_LINES,
    MAX_GIT_DIFF_OUTPUT_BYTES,
    MAX_GIT_EXECUTABLE_BYTES,
    MAX_GIT_STAGE_FILE_BYTES,
    MAX_GIT_STATUS_ENTRIES,
    MAX_GIT_UNSTAGE_FILE_BYTES,
    WindowsLocalGitAdapter,
)

_EXPECTED_GIT_EXECUTABLE_PATH = "_expected_git_executable_path"
_EXPECTED_GIT_EXECUTABLE_SHA256 = "_expected_git_executable_sha256"




_EXPECTED_GIT_DIFF_PATH = "_expected_git_diff_path"
_EXPECTED_GIT_DIFF_TARGET_SHA256 = "_expected_git_diff_target_sha256"
_EXPECTED_GIT_DIFF_HEAD_SHA256 = "_expected_git_diff_head_sha256"

_EXPECTED_GIT_STAGE_PATH = "_expected_git_stage_path"
_EXPECTED_GIT_STAGE_TARGET_SHA256 = "_expected_git_stage_target_sha256"
_EXPECTED_GIT_STAGE_HEAD_SHA256 = "_expected_git_stage_head_sha256"


class GitDiffFileAction:
    name = "git_diff_file"

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = request.arguments.get("path")
        if isinstance(raw_path, str) and _is_privileged_read_path(raw_path):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_DIFF_PATH_INVALID": (
                "O caminho Git precisa ser relativo, explícito e sem traversal."
            ),
            "GIT_DIFF_FILE_NOT_FOUND": (
                "O arquivo solicitado não existe no checkout atual."
            ),
            "GIT_DIFF_FILE_REQUIRED": (
                "A inspeção de diff aceita somente um arquivo regular existente."
            ),
            "GIT_DIFF_LINK_NOT_ALLOWED": (
                "Links e junctions não são aceitos na inspeção de diff."
            ),
            "GIT_DIFF_PATH_OUTSIDE_REPOSITORY": (
                "O caminho resolvido saiu do checkout fixo."
            ),
            "GIT_DIFF_TARGET_UNAVAILABLE": (
                "Não foi possível ler o arquivo alvo com segurança."
            ),
            "GIT_DIFF_FILE_TOO_LARGE": (
                "O arquivo excede o limite local de 256 KiB."
            ),
            "GIT_DIFF_BINARY_NOT_ALLOWED": (
                "Arquivo binário não é aceito nesta fronteira de diff textual."
            ),
            "GIT_DIFF_TRACKED_FILE_REQUIRED": (
                "O M84 aceita somente arquivo já rastreado pelo Git."
            ),
            "GIT_DIFF_NO_CHANGES": (
                "O arquivo não possui diferença contra HEAD."
            ),
            "GIT_DIFF_PREFLIGHT_FAILED": (
                "Não foi possível validar o diff local antes da confirmação."
            ),
            "GIT_DIFF_TIMEOUT": (
                "A validação do diff excedeu o timeout local."
            ),
            "GIT_DIFF_TARGET_CHANGED_DURING_PREVIEW": (
                "O arquivo mudou durante a preparação da prévia."
            ),
            "GIT_EXECUTABLE_CHANGED_DURING_PREVIEW": (
                "O git.exe mudou durante a preparação da prévia."
            ),
            "GIT_EXECUTABLE_NOT_AVAILABLE": "O git.exe local não está disponível.",
            "GIT_EXECUTABLE_LINK_NOT_ALLOWED": (
                "O git.exe local não pode ser link/junction."
            ),
            "GIT_EXECUTABLE_TOO_LARGE": (
                "O git.exe local excede o limite de identidade."
            ),
            "GIT_EXECUTABLE_UNREADABLE": (
                "Não foi possível hashear o git.exe local."
            ),
            "GIT_REPOSITORY_NOT_AVAILABLE": (
                "O checkout Git fixo não está disponível."
            ),
            "GIT_REPOSITORY_ROOT_MISMATCH": (
                "A raiz Git resolvida não corresponde ao checkout fixo."
            ),
            "GIT_HEAD_NOT_AVAILABLE": "Não foi possível ler o HEAD Git.",
            "GIT_HEAD_OUTPUT_INVALID": "O HEAD Git retornou formato inválido.",
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar a inspeção de diff local.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = request.arguments.get("path")
        if not isinstance(raw_path, str):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho inválido.",
            )
        try:
            evidence = self._git.preview_diff_target(raw_path)
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a inspeção de diff local.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        target_sha256 = str(evidence["target_sha256"])
        head_sha256 = str(evidence["head_sha"])
        git_path = str(evidence["git_executable_path"])
        git_sha256 = str(evidence["git_executable_sha256"])
        file_size = int(evidence["file_size_bytes"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR DIFF GIT DE UM ARQUIVO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Arquivo aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"Tamanho atual: {file_size} byte(s); limite de "
                f"{MAX_GIT_DIFF_FILE_BYTES} byte(s).\n"
                f"HEAD aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Após esta confirmação, THE OS coletará somente o diff textual desse "
                "arquivo contra o HEAD aprovado, usando argv fixo, --no-ext-diff, "
                "--no-textconv e sem shell. O conteúdo do diff será enviado ao provedor "
                "como dado não confiável.\n"
                f"Limites do retorno: {MAX_GIT_DIFF_OUTPUT_BYTES} byte(s) e "
                f"{MAX_GIT_DIFF_LINES} linhas. Arquivos não rastreados, deletados, "
                "binários e links ficam fora desta fronteira. Nenhuma operação de "
                "stage, commit, checkout, reset, fetch, pull ou push é autorizada."
            ),
            execution_guard={
                _EXPECTED_GIT_DIFF_PATH: path,
                _EXPECTED_GIT_DIFF_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_DIFF_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = request.arguments.get("path")
        expected_path = request.arguments.get(_EXPECTED_GIT_DIFF_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_DIFF_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_DIFF_HEAD_SHA256
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(raw_path, str)
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_target_sha256, str)
            or len(expected_target_sha256) != 64
            or not isinstance(expected_head_sha256, str)
            or len(expected_head_sha256) not in {40, 64}
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A inspeção de diff exige a prévia local aprovada.",
                error_code="GIT_DIFF_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.diff_file(
                raw_path,
                expected_path=expected_path,
                expected_target_sha256=expected_target_sha256,
                expected_head_sha256=expected_head_sha256,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui coletar o diff Git local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_DIFF_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_DIFF_PATH_CHANGED_AFTER_PREVIEW": (
                    "O caminho resolvido mudou após a aprovação; diff bloqueado."
                ),
                "GIT_DIFF_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo mudou após a aprovação; diff bloqueado."
                ),
                "GIT_DIFF_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; diff bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; diff bloqueado."
                ),
                "GIT_DIFF_STATE_CHANGED_DURING_READ": (
                    "O estado Git/arquivo mudou durante a leitura; diff descartado."
                ),
                "GIT_DIFF_OUTPUT_TOO_LARGE": (
                    "O diff excede o limite local de 32 KiB."
                ),
                "GIT_DIFF_LINE_LIMIT_EXCEEDED": (
                    "O diff excede o limite local de 400 linhas."
                ),
                "GIT_DIFF_OUTPUT_ENCODING_FAILED": (
                    "O diff não pôde ser decodificado como UTF-8."
                ),
                "GIT_DIFF_OUTPUT_INVALID": "O diff retornou formato inválido.",
                "GIT_DIFF_EMPTY_UNEXPECTED": (
                    "O Git não retornou conteúdo de diff apesar da prévia."
                ),
                "GIT_DIFF_TIMEOUT": "A coleta do diff excedeu o timeout local.",
                "GIT_DIFF_FAILED": "A coleta do diff Git falhou.",
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "A inspeção de diff foi bloqueada."),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Diff Git coletado para {expected_path}: "
                f"{evidence['diff_bytes']} byte(s), "
                f"{evidence['diff_lines']} linha(s)."
            ),
            evidence=evidence,
        )



_EXPECTED_GIT_STAGE_PATH = "_expected_git_stage_path"
_EXPECTED_GIT_STAGE_TARGET_SHA256 = "_expected_git_stage_target_sha256"
_EXPECTED_GIT_STAGE_HEAD_SHA256 = "_expected_git_stage_head_sha256"


class GitStageFileAction:
    name = "git_stage_file"

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = request.arguments.get("path")
        if isinstance(raw_path, str) and _is_privileged_read_path(raw_path):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_DIFF_PATH_INVALID": (
                "O caminho Git precisa ser relativo, explícito e sem traversal."
            ),
            "GIT_DIFF_FILE_NOT_FOUND": (
                "O arquivo solicitado não existe no checkout atual."
            ),
            "GIT_DIFF_FILE_REQUIRED": (
                "O stage aceita somente um arquivo regular existente."
            ),
            "GIT_DIFF_LINK_NOT_ALLOWED": (
                "Links e junctions não são aceitos nesta fronteira de stage."
            ),
            "GIT_DIFF_PATH_OUTSIDE_REPOSITORY": (
                "O caminho resolvido saiu do checkout fixo."
            ),
            "GIT_DIFF_TARGET_UNAVAILABLE": (
                "Não foi possível ler o arquivo alvo com segurança."
            ),
            "GIT_DIFF_FILE_TOO_LARGE": (
                "O arquivo excede o limite local de 256 KiB."
            ),
            "GIT_DIFF_BINARY_NOT_ALLOWED": (
                "Arquivo binário não é aceito nesta primeira fronteira de stage."
            ),
            "GIT_DIFF_TRACKED_FILE_REQUIRED": (
                "O M85 aceita somente arquivo já rastreado pelo Git."
            ),
            "GIT_DIFF_NO_CHANGES": (
                "O arquivo não possui diferença contra HEAD."
            ),
            "GIT_STAGE_REQUIRES_EMPTY_INDEX": (
                "O M85 exige índice Git vazio antes do stage."
            ),
            "GIT_STAGE_TARGET_STATUS_FAILED": (
                "Não foi possível confirmar o estado unstaged do arquivo."
            ),
            "GIT_STAGE_TARGET_NOT_UNSTAGED_MODIFICATION": (
                "O M85 aceita somente modificação rastreada e ainda não staged."
            ),
            "GIT_STAGE_TIMEOUT": "A validação local de stage excedeu o timeout.",
            "GIT_STAGE_PREFLIGHT_FAILED": (
                "Não foi possível validar o stage local antes da confirmação."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o stage Git local.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = request.arguments.get("path")
        if not isinstance(raw_path, str):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho inválido.",
            )
        try:
            evidence = self._git.preview_stage_target(raw_path)
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o stage Git local.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        target_sha256 = str(evidence["target_sha256"])
        head_sha256 = str(evidence["head_sha"])
        git_path = str(evidence["git_executable_path"])
        git_sha256 = str(evidence["git_executable_sha256"])
        file_size = int(evidence["file_size_bytes"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "PREPARAR STAGE GIT DE UM ARQUIVO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Arquivo aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"Tamanho atual: {file_size} byte(s); limite de "
                f"{MAX_GIT_STAGE_FILE_BYTES} byte(s).\n"
                f"HEAD aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Índice Git atual: vazio; o alvo é uma modificação rastreada ainda "
                "não staged.\n"
                "Após esta confirmação, THE OS executará somente git add -- <path> "
                "para este arquivo aprovado, sem shell. A operação modificará somente "
                "o índice Git; o conteúdo do working tree deve permanecer inalterado. "
                "Se a pós-validação falhar, THE OS pode executar somente um reset "
                "bounded do mesmo path para restaurar o índice vazio. Nenhum commit, "
                "checkout, fetch, pull, push, remote, revisão ou flag fornecida pelo "
                "modelo é autorizada."
            ),
            execution_guard={
                _EXPECTED_GIT_STAGE_PATH: path,
                _EXPECTED_GIT_STAGE_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_STAGE_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = request.arguments.get("path")
        expected_path = request.arguments.get(_EXPECTED_GIT_STAGE_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_STAGE_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_STAGE_HEAD_SHA256
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(raw_path, str)
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_target_sha256, str)
            or len(expected_target_sha256) != 64
            or not isinstance(expected_head_sha256, str)
            or len(expected_head_sha256) not in {40, 64}
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O stage Git exige a prévia local aprovada.",
                error_code="GIT_STAGE_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.stage_file(
                raw_path,
                expected_path=expected_path,
                expected_target_sha256=expected_target_sha256,
                expected_head_sha256=expected_head_sha256,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui concluir o stage Git local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_STAGE_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_STAGE_PATH_CHANGED_AFTER_PREVIEW": (
                    "O caminho resolvido mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; stage bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_REQUIRES_EMPTY_INDEX": (
                    "O índice Git deixou de estar vazio; stage bloqueado."
                ),
                "GIT_STAGE_TARGET_NOT_UNSTAGED_MODIFICATION": (
                    "O alvo deixou de ser uma modificação rastreada unstaged."
                ),
                "GIT_STAGE_TIMEOUT": "A operação de stage excedeu o timeout local.",
                "GIT_STAGE_FAILED": "A operação de stage Git falhou.",
                "GIT_STAGE_POSTCONDITION_FAILED": (
                    "O stage não atingiu a pós-condição exata e foi revertido quando possível."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "O stage Git foi bloqueado."),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Stage Git verificado para {expected_path}: "
                "o índice contém somente esse arquivo e o working tree do alvo "
                "permaneceu inalterado."
            ),
            evidence=evidence,
        )


_EXPECTED_GIT_UNSTAGE_PATH = "_expected_git_unstage_path"
_EXPECTED_GIT_UNSTAGE_TARGET_SHA256 = "_expected_git_unstage_target_sha256"
_EXPECTED_GIT_UNSTAGE_HEAD_SHA256 = "_expected_git_unstage_head_sha256"


class GitUnstageFileAction:
    name = "git_unstage_file"

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        raw_path = request.arguments.get("path")
        if isinstance(raw_path, str) and _is_privileged_read_path(raw_path):
            return ActionRisk.PRIVILEGED
        return ActionRisk.CONFIRM

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_DIFF_PATH_INVALID": (
                "O caminho Git precisa ser relativo, explícito e sem traversal."
            ),
            "GIT_DIFF_FILE_NOT_FOUND": (
                "O arquivo solicitado não existe no checkout atual."
            ),
            "GIT_DIFF_FILE_REQUIRED": (
                "O unstage aceita somente um arquivo regular existente."
            ),
            "GIT_DIFF_LINK_NOT_ALLOWED": (
                "Links e junctions não são aceitos nesta fronteira de unstage."
            ),
            "GIT_DIFF_PATH_OUTSIDE_REPOSITORY": (
                "O caminho resolvido saiu do checkout fixo."
            ),
            "GIT_DIFF_TARGET_UNAVAILABLE": (
                "Não foi possível ler o arquivo alvo com segurança."
            ),
            "GIT_DIFF_FILE_TOO_LARGE": (
                "O arquivo excede o limite local de 256 KiB."
            ),
            "GIT_DIFF_BINARY_NOT_ALLOWED": (
                "Arquivo binário não é aceito nesta primeira fronteira de unstage."
            ),
            "GIT_DIFF_TRACKED_FILE_REQUIRED": (
                "O M86 aceita somente arquivo já rastreado pelo Git."
            ),
            "GIT_DIFF_NO_CHANGES": (
                "O arquivo não possui diferença contra HEAD."
            ),
            "GIT_UNSTAGE_REQUIRES_ONLY_TARGET_STAGED": (
                "O M86 exige que o índice contenha somente o arquivo solicitado."
            ),
            "GIT_STAGE_TARGET_STATUS_FAILED": (
                "Não foi possível confirmar o estado staged do arquivo."
            ),
            "GIT_UNSTAGE_TARGET_NOT_STAGED_MODIFICATION": (
                "O M86 aceita somente uma modificação rastreada staged e sem mudança unstaged."
            ),
            "GIT_UNSTAGE_TIMEOUT": (
                "A validação local de unstage excedeu o timeout."
            ),
            "GIT_UNSTAGE_PREFLIGHT_FAILED": (
                "Não foi possível validar o unstage local antes da confirmação."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o unstage Git local.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = request.arguments.get("path")
        if not isinstance(raw_path, str):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho inválido.",
            )
        try:
            evidence = self._git.preview_unstage_target(raw_path)
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o unstage Git local.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        target_sha256 = str(evidence["target_sha256"])
        head_sha256 = str(evidence["head_sha"])
        git_path = str(evidence["git_executable_path"])
        git_sha256 = str(evidence["git_executable_sha256"])
        file_size = int(evidence["file_size_bytes"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "REMOVER STAGE GIT DE UM ARQUIVO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Arquivo aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"Tamanho atual: {file_size} byte(s); limite de "
                f"{MAX_GIT_UNSTAGE_FILE_BYTES} byte(s).\n"
                f"HEAD aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Índice Git atual: contém somente esse arquivo como modificação staged, "
                "sem mudança unstaged no alvo.\n"
                "Após esta confirmação, THE OS executará somente "
                "git reset --quiet HEAD -- <path> para este arquivo aprovado, sem shell. "
                "A operação modificará somente o índice Git; o conteúdo do working tree "
                "deve permanecer inalterado. Se a pós-validação falhar, THE OS pode "
                "executar somente git add -- <path> no mesmo alvo para restaurar o stage "
                "anterior. Nenhum commit, checkout, fetch, pull, push, remote, revisão ou "
                "flag fornecida pelo modelo é autorizada."
            ),
            execution_guard={
                _EXPECTED_GIT_UNSTAGE_PATH: path,
                _EXPECTED_GIT_UNSTAGE_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_UNSTAGE_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = request.arguments.get("path")
        expected_path = request.arguments.get(_EXPECTED_GIT_UNSTAGE_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_UNSTAGE_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_UNSTAGE_HEAD_SHA256
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(raw_path, str)
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_target_sha256, str)
            or len(expected_target_sha256) != 64
            or not isinstance(expected_head_sha256, str)
            or len(expected_head_sha256) not in {40, 64}
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O unstage Git exige a prévia local aprovada.",
                error_code="GIT_UNSTAGE_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.unstage_file(
                raw_path,
                expected_path=expected_path,
                expected_target_sha256=expected_target_sha256,
                expected_head_sha256=expected_head_sha256,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui concluir o unstage Git local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_UNSTAGE_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_UNSTAGE_PATH_CHANGED_AFTER_PREVIEW": (
                    "O caminho resolvido mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_REQUIRES_ONLY_TARGET_STAGED": (
                    "O índice Git deixou de conter somente o alvo aprovado."
                ),
                "GIT_UNSTAGE_TARGET_NOT_STAGED_MODIFICATION": (
                    "O alvo deixou de ser uma modificação staged limpa no working tree."
                ),
                "GIT_UNSTAGE_TIMEOUT": (
                    "A operação de unstage excedeu o timeout local."
                ),
                "GIT_UNSTAGE_FAILED": "A operação de unstage Git falhou.",
                "GIT_UNSTAGE_POSTCONDITION_FAILED": (
                    "O unstage não atingiu a pós-condição exata e o stage anterior foi restaurado quando possível."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "O unstage Git foi bloqueado."),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Unstage Git verificado para {expected_path}: "
                "o índice ficou vazio e o working tree do alvo permaneceu inalterado."
            ),
            evidence=evidence,
        )



class GitStatusSnapshotAction:
    name = "git_status_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_EXECUTABLE_NOT_AVAILABLE": (
                "O git.exe local não está disponível."
            ),
            "GIT_EXECUTABLE_LINK_NOT_ALLOWED": (
                "O git.exe local não pode ser link/junction."
            ),
            "GIT_EXECUTABLE_TOO_LARGE": (
                "O git.exe local excede o limite de identidade."
            ),
            "GIT_EXECUTABLE_UNREADABLE": (
                "Não foi possível hashear o git.exe local."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o snapshot Git local.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        _ = request
        try:
            verifier = self._git.preview_git_executable()
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível validar o git.exe local.",
            )
        if verifier.get("error") is not None:
            return self._blocked_preview(verifier)

        git_path = str(verifier["git_executable_path"])
        git_sha256 = str(verifier["git_executable_sha256"])
        git_size = int(verifier["git_executable_size_bytes"])
        repository_root = str(verifier["repository_root"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR STATUS GIT LOCAL\n"
                f"Repositório fixo: {repository_root}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                f"git.exe: {git_size} byte(s); limite de "
                f"{MAX_GIT_EXECUTABLE_BYTES} byte(s).\n"
                "Após a confirmação, THE OS executará somente comandos Git fixos "
                "de leitura para validar a raiz do próprio checkout, ler HEAD/branch "
                "e coletar git status porcelain. O modelo não escolhe repositório, "
                "subcomando, flag ou executável.\n"
                f"Serão enviados ao provedor somente branch, HEAD, estado clean/dirty "
                f"e até {MAX_GIT_STATUS_ENTRIES} caminhos alterados com status "
                "index/worktree. Conteúdo de diff, blobs, mensagens de commit, remotes, "
                "credenciais, stdout/stderr brutos e conteúdo de arquivos não são "
                "coletados. GIT_* herdadas são removidas e GIT_OPTIONAL_LOCKS=0."
            ),
            execution_guard={
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        expected_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_sha256 = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_SHA256)
        if (
            not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O snapshot Git exige a prévia local aprovada.",
                error_code="GIT_STATUS_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.snapshot(
                expected_git_executable_path=expected_path,
                expected_git_executable_sha256=expected_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui coletar o status Git local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_STATUS_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; o status não foi coletado."
                ),
                "GIT_EXECUTABLE_CHANGED_DURING_STATUS": (
                    "O git.exe mudou durante a coleta; o snapshot foi descartado."
                ),
                "GIT_REPOSITORY_NOT_AVAILABLE": (
                    "O checkout Git fixo não está disponível."
                ),
                "GIT_REPOSITORY_ROOT_MISMATCH": (
                    "A raiz Git resolvida não corresponde ao checkout fixo."
                ),
                "GIT_HEAD_NOT_AVAILABLE": "Não foi possível ler o HEAD Git.",
                "GIT_HEAD_OUTPUT_INVALID": "O HEAD Git retornou formato inválido.",
                "GIT_BRANCH_READ_FAILED": "Não foi possível ler a branch Git.",
                "GIT_STATUS_OUTPUT_TOO_LARGE": (
                    "A saída do status Git excedeu o limite local."
                ),
                "GIT_STATUS_OUTPUT_ENCODING_FAILED": (
                    "A saída do status Git não pôde ser decodificada com segurança."
                ),
                "GIT_STATUS_OUTPUT_INVALID": (
                    "A saída porcelain do Git não corresponde ao formato esperado."
                ),
                "GIT_STATUS_TIMEOUT": "A inspeção Git excedeu o timeout local.",
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "Não consegui coletar o status Git local."),
                evidence=evidence,
                error_code=error,
            )

        branch = evidence.get("branch")
        branch_text = (
            str(branch)
            if isinstance(branch, str)
            else f"detached@{str(evidence['head_sha'])[:12]}"
        )
        observed = int(evidence["observed_changes"])
        returned = int(evidence["returned_changes"])
        state = "limpo" if bool(evidence["clean"]) else "com alterações"

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Status Git coletado: {branch_text}, {state}; "
                f"{observed} alteração(ões) observada(s), "
                f"{returned} retornada(s)."
            ),
            evidence=evidence,
        )
