from __future__ import annotations

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.git_local import (
    MAX_GIT_EXECUTABLE_BYTES,
    MAX_GIT_STATUS_ENTRIES,
    WindowsLocalGitAdapter,
)

_EXPECTED_GIT_EXECUTABLE_PATH = "_expected_git_executable_path"
_EXPECTED_GIT_EXECUTABLE_SHA256 = "_expected_git_executable_sha256"


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
