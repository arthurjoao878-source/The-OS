from __future__ import annotations

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.actions.file_system import _is_privileged_read_path
from theos.integrations.windows.git_local import (
    FIXED_GIT_COMMIT_MESSAGE,
    FIXED_GIT_COMMIT_NEW_FILE_MESSAGE,
    FIXED_GIT_REMOTE_BRANCH,
    FIXED_GIT_REMOTE_NAME,
    FIXED_GIT_REMOTE_REF,
    FIXED_GIT_REMOTE_TRACKING_REF,
    FIXED_GIT_REMOTE_URL,
    MAX_GIT_DIFF_FILE_BYTES,
    MAX_GIT_DIFF_LINES,
    MAX_GIT_DIFF_OUTPUT_BYTES,
    MAX_GIT_EXECUTABLE_BYTES,
    MAX_GIT_STAGE_FILE_BYTES,
    MAX_GIT_STAGE_NEW_FILE_BYTES,
    MAX_GIT_STATUS_ENTRIES,
    MAX_GIT_UNSTAGE_FILE_BYTES,
    WindowsLocalGitAdapter,
)

_EXPECTED_GIT_EXECUTABLE_PATH = "_expected_git_executable_path"
_EXPECTED_GIT_EXECUTABLE_SHA256 = "_expected_git_executable_sha256"




_EXPECTED_GIT_FETCH_LOCAL_HEAD = "_expected_git_fetch_local_head"
_EXPECTED_GIT_FETCH_TRACKING_REF = "_expected_git_fetch_tracking_ref"
_EXPECTED_GIT_FETCH_STATUS_DIGEST = "_expected_git_fetch_status_digest"
_EXPECTED_GIT_FETCH_REFS_DIGEST = "_expected_git_fetch_refs_digest"


class GitFetchRemoteMainAction:
    name = "git_fetch_remote_main"
    risk = ActionRisk.CONFIRM

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_FETCH_REMOTE_MAIN_LOCAL_IDENTITY_INVALID": (
                "A identidade local M91 não corresponde ao remote autorizado."
            ),
            "GIT_FETCH_REMOTE_MAIN_LOCAL_TRANSPORT_OVERRIDE_NOT_ALLOWED": (
                "Há configuração Git local de transporte/fetch fora da política do M93."
            ),
            "GIT_FETCH_REMOTE_MAIN_SHALLOW_REPOSITORY_NOT_ALLOWED": (
                "O primeiro fetch controlado não aceita repositório shallow."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o fetch Git controlado de main.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        _ = request
        try:
            evidence = self._git.preview_fetch_remote_main()
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o fetch Git controlado de main.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        tracking_before = (
            str(evidence["tracking_ref_before"])
            if evidence["tracking_ref_before"] is not None
            else "__ABSENT__"
        )

        return ConfirmationPreview(
            allowed=True,
            text=(
                "ATUALIZAR SNAPSHOT LOCAL DE origin/main POR FETCH CONTROLADO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"URL remota fixa: {FIXED_GIT_REMOTE_URL}\n"
                f"Ref remota fonte fixa: {FIXED_GIT_REMOTE_REF}\n"
                f"Ref local de destino fixa: {FIXED_GIT_REMOTE_TRACKING_REF}\n"
                f"HEAD local aprovado: {evidence['head_sha']}\n"
                f"Ref local atual: {tracking_before}\n"
                f"git.exe aprovado: {evidence['git_executable_path']}\n"
                f"SHA-256 do git.exe: {evidence['git_executable_sha256']}\n"
                "Após esta confirmação, THE OS primeiro relerá o HEAD remoto via M92, "
                "fará um fetch HTTPS fixo de objetos de refs/heads/main sem escrever "
                "FETCH_HEAD, tags, commit-graph, submódulos ou outras refs, relerá o "
                "HEAD remoto e então poderá atualizar somente refs/remotes/origin/main "
                "para o SHA observado. A atualização é bloqueada se a ref remota mudar "
                "durante o fetch ou se a ref local existente exigiria movimento "
                "non-fast-forward.\n"
                "Working tree, índice, HEAD/branch local e todas as outras refs devem "
                "permanecer idênticos. Credential helper/askpass são desabilitados, "
                "configs global/system e proxies herdados são ignorados. Nenhum pull "
                "ou push é autorizado."
            ),
            execution_guard={
                _EXPECTED_GIT_FETCH_LOCAL_HEAD: str(evidence["head_sha"]),
                _EXPECTED_GIT_FETCH_TRACKING_REF: tracking_before,
                _EXPECTED_GIT_FETCH_STATUS_DIGEST: str(evidence["status_digest"]),
                _EXPECTED_GIT_FETCH_REFS_DIGEST: str(evidence["refs_digest"]),
                _EXPECTED_GIT_EXECUTABLE_PATH: str(evidence["git_executable_path"]),
                _EXPECTED_GIT_EXECUTABLE_SHA256: str(
                    evidence["git_executable_sha256"]
                ),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        expected_local_head = request.arguments.get(_EXPECTED_GIT_FETCH_LOCAL_HEAD)
        expected_tracking_ref = request.arguments.get(
            _EXPECTED_GIT_FETCH_TRACKING_REF
        )
        expected_status_digest = request.arguments.get(
            _EXPECTED_GIT_FETCH_STATUS_DIGEST
        )
        expected_refs_digest = request.arguments.get(_EXPECTED_GIT_FETCH_REFS_DIGEST)
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(expected_local_head, str)
            or len(expected_local_head) not in {40, 64}
            or not isinstance(expected_tracking_ref, str)
            or not expected_tracking_ref
            or not isinstance(expected_status_digest, str)
            or len(expected_status_digest) != 64
            or not isinstance(expected_refs_digest, str)
            or len(expected_refs_digest) != 64
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O fetch Git controlado exige a prévia local aprovada.",
                error_code="GIT_FETCH_REMOTE_MAIN_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.fetch_remote_main(
                expected_local_head_sha256=expected_local_head,
                expected_tracking_ref_sha256=expected_tracking_ref,
                expected_status_digest=expected_status_digest,
                expected_refs_digest=expected_refs_digest,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui concluir o fetch Git controlado.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_FETCH_REMOTE_MAIN_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_FETCH_REMOTE_MAIN_LOCAL_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD local mudou após a aprovação; fetch bloqueado."
                ),
                "GIT_FETCH_REMOTE_MAIN_TRACKING_REF_CHANGED_AFTER_PREVIEW": (
                    "A ref refs/remotes/origin/main mudou após a aprovação."
                ),
                "GIT_FETCH_REMOTE_MAIN_WORKTREE_STATE_CHANGED_AFTER_PREVIEW": (
                    "O estado do working tree/índice mudou após a aprovação."
                ),
                "GIT_FETCH_REMOTE_MAIN_REFS_CHANGED_AFTER_PREVIEW": (
                    "Alguma ref local mudou após a aprovação."
                ),
                "GIT_FETCH_REMOTE_MAIN_REMOTE_HEAD_READ_FAILED": (
                    "Não foi possível obter o HEAD remoto autorizado antes do fetch."
                ),
                "GIT_FETCH_REMOTE_MAIN_TIMEOUT": (
                    "O fetch controlado excedeu o timeout bounded."
                ),
                "GIT_FETCH_REMOTE_MAIN_FAILED": (
                    "O fetch controlado de objetos falhou."
                ),
                "GIT_FETCH_REMOTE_MAIN_UNEXPECTED_REF_MUTATION_DURING_FETCH": (
                    "O subprocesso fetch alterou uma ref local antes da atualização autorizada."
                ),
                "GIT_FETCH_REMOTE_MAIN_WORKTREE_STATE_CHANGED_DURING_FETCH": (
                    "O fetch alterou working tree ou índice; operação bloqueada."
                ),
                "GIT_FETCH_REMOTE_MAIN_REMOTE_CHANGED_DURING_FETCH": (
                    "refs/heads/main mudou no remoto durante o fetch; a ref local não foi atualizada."
                ),
                "GIT_FETCH_REMOTE_MAIN_NON_FAST_FORWARD_BLOCKED": (
                    "A atualização de refs/remotes/origin/main exigiria movimento non-fast-forward."
                ),
                "GIT_FETCH_REMOTE_MAIN_REF_UPDATE_FAILED": (
                    "A atualização atômica da única ref local autorizada falhou."
                ),
                "GIT_FETCH_REMOTE_MAIN_POSTCONDITION_FAILED": (
                    "A pós-condição do fetch controlado não pôde ser comprovada."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    error,
                    "O fetch Git controlado foi bloqueado.",
                ),
                evidence=evidence,
                error_code=error,
            )

        movement = (
            "atualizada"
            if evidence["tracking_ref_changed"]
            else "já estava no SHA remoto"
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Fetch controlado concluído: {FIXED_GIT_REMOTE_TRACKING_REF} "
                f"{movement} em {evidence['tracking_ref_after']}. "
                "HEAD/branch local, índice e working tree permaneceram inalterados; "
                "nenhum push foi realizado."
            ),
            evidence=evidence,
        )


_EXPECTED_GIT_REMOTE_HEAD_LOCAL_HEAD = "_expected_git_remote_head_local_head"


class GitRemoteHeadSnapshotAction:
    name = "git_remote_head_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        return ConfirmationPreview(
            allowed=False,
            text=(
                "Não foi possível preparar a leitura remota de HEAD porque a identidade "
                "Git local autorizada não pôde ser validada exatamente."
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

        try:
            local_identity = self._git.remote_identity_snapshot(
                expected_git_executable_path=git_path,
                expected_git_executable_sha256=git_sha256,
            )
        except (OSError, RuntimeError, ValueError):
            return self._blocked_preview({})
        if local_identity.get("error") is not None:
            return self._blocked_preview(local_identity)

        local_head = str(local_identity["head_sha"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "LER HEAD REMOTO GIT AUTORIZADO\n"
                f"Repositório local fixo: {local_identity['repository_root']}\n"
                f"Remote local validado: {FIXED_GIT_REMOTE_NAME}\n"
                f"URL remota fixa: {FIXED_GIT_REMOTE_URL}\n"
                f"Ref remota fixa: {FIXED_GIT_REMOTE_REF}\n"
                f"HEAD local aprovado: {local_head}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Após esta confirmação, THE OS fará um único contato de rede read-only "
                "usando somente `git ls-remote --exit-code --heads` contra a URL HTTPS e "
                "ref fixas acima. A chamada ocorrerá fora do checkout, com configurações "
                "Git global/system ignoradas, credential helper e askpass desabilitados, "
                "variáveis de proxy removidas e redirects HTTP desabilitados. Antes e "
                "depois da rede, a identidade local M91 e o HEAD local serão revalidados.\n"
                "Nenhum fetch, pull, push, alteração de refs locais, working tree, índice "
                "ou histórico Git é autorizado."
            ),
            execution_guard={
                _EXPECTED_GIT_REMOTE_HEAD_LOCAL_HEAD: local_head,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        expected_local_head = request.arguments.get(
            _EXPECTED_GIT_REMOTE_HEAD_LOCAL_HEAD
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(expected_local_head, str)
            or len(expected_local_head) not in {40, 64}
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A leitura remota de HEAD exige a prévia local aprovada.",
                error_code="GIT_REMOTE_HEAD_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.remote_head_snapshot(
                expected_local_head_sha256=expected_local_head,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ler o HEAD remoto autorizado.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_REMOTE_HEAD_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_REMOTE_HEAD_LOCAL_IDENTITY_INVALID": (
                    "A identidade Git local deixou de corresponder ao remote autorizado."
                ),
                "GIT_REMOTE_HEAD_LOCAL_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD local mudou após a aprovação; leitura remota bloqueada."
                ),
                "GIT_REMOTE_HEAD_TIMEOUT": (
                    "A leitura do HEAD remoto excedeu o timeout bounded."
                ),
                "GIT_REMOTE_HEAD_FAILED": (
                    "A leitura read-only do HEAD remoto falhou."
                ),
                "GIT_REMOTE_HEAD_OUTPUT_TOO_LARGE": (
                    "A resposta remota excedeu o limite bounded."
                ),
                "GIT_REMOTE_HEAD_OUTPUT_ENCODING_FAILED": (
                    "A resposta remota não possui encoding esperado."
                ),
                "GIT_REMOTE_HEAD_OUTPUT_INVALID": (
                    "A resposta remota não corresponde exatamente à única ref main autorizada."
                ),
                "GIT_REMOTE_HEAD_LOCAL_IDENTITY_CHANGED_DURING_READ": (
                    "A identidade Git local mudou durante a leitura remota."
                ),
                "GIT_REMOTE_HEAD_LOCAL_HEAD_CHANGED_DURING_READ": (
                    "O HEAD local mudou durante a leitura remota."
                ),
                "GIT_EXECUTABLE_CHANGED_DURING_REMOTE_HEAD_READ": (
                    "O git.exe mudou durante a leitura remota."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    error,
                    "A leitura remota de HEAD foi bloqueada.",
                ),
                evidence=evidence,
                error_code=error,
            )

        relation = (
            "corresponde ao HEAD local"
            if evidence["remote_matches_local_head"]
            else "difere do HEAD local"
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"HEAD remoto verificado para {FIXED_GIT_REMOTE_REF}: "
                f"{evidence['remote_head_sha']}; {relation}. "
                "Nenhuma ref local ou arquivo foi alterado."
            ),
            evidence=evidence,
        )


class GitRemoteIdentitySnapshotAction:
    name = "git_remote_identity_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
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
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar a inspeção da identidade Git remota.",
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
        repository_root = str(verifier["repository_root"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR IDENTIDADE GIT REMOTA LOCAL\n"
                f"Repositório fixo: {repository_root}\n"
                f"Remote autorizado esperado: {FIXED_GIT_REMOTE_NAME}\n"
                f"URL autorizada esperada: {FIXED_GIT_REMOTE_URL}\n"
                f"Branch autorizada esperada: {FIXED_GIT_REMOTE_BRANCH}\n"
                f"Ref remota autorizada esperada: {FIXED_GIT_REMOTE_REF}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Após esta confirmação, THE OS fará somente leituras Git locais e "
                "fixas do checkout e de .git/config para provar que origin/main "
                "correspondem exatamente à identidade autorizada. Configurações locais "
                "de pushurl, push refspec, pushDefault, branch pushRemote, receivepack, "
                "uploadpack, core.sshCommand e url.*.insteadOf são bloqueadas.\n"
                "Nenhum contato de rede será feito: não há ls-remote, fetch, pull ou "
                "push. Valores configurados divergentes não são enviados ao provedor; "
                "apenas a classe de mismatch é retornada."
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
                message="A inspeção da identidade remota exige a prévia local aprovada.",
                error_code="GIT_REMOTE_IDENTITY_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.remote_identity_snapshot(
                expected_git_executable_path=expected_path,
                expected_git_executable_sha256=expected_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui validar a identidade Git remota local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_REMOTE_IDENTITY_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_REMOTE_IDENTITY_ROOT_MISMATCH": (
                    "A raiz Git não corresponde ao checkout fixo autorizado."
                ),
                "GIT_REMOTE_IDENTITY_BRANCH_MISMATCH": (
                    "A branch local atual não é a branch main autorizada."
                ),
                "GIT_REMOTE_IDENTITY_URL_MISMATCH": (
                    "A URL local de origin não corresponde ao remoto autorizado."
                ),
                "GIT_REMOTE_IDENTITY_FETCH_REFSPEC_MISMATCH": (
                    "O refspec local de fetch de origin não corresponde à política autorizada."
                ),
                "GIT_REMOTE_IDENTITY_TRACKING_REMOTE_MISMATCH": (
                    "main não rastreia exatamente o remote origin autorizado."
                ),
                "GIT_REMOTE_IDENTITY_TRACKING_REF_MISMATCH": (
                    "main não rastreia exatamente refs/heads/main."
                ),
                "GIT_REMOTE_IDENTITY_PUSHURL_NOT_ALLOWED": (
                    "origin possui pushurl local, o que não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_PUSH_REFSPEC_NOT_ALLOWED": (
                    "origin possui push refspec local, o que não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_PUSH_DEFAULT_NOT_ALLOWED": (
                    "remote.pushDefault local não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_BRANCH_PUSH_REMOTE_NOT_ALLOWED": (
                    "branch.main.pushRemote local não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_RECEIVEPACK_NOT_ALLOWED": (
                    "remote.origin.receivepack local não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_UPLOADPACK_NOT_ALLOWED": (
                    "remote.origin.uploadpack local não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_SSH_COMMAND_NOT_ALLOWED": (
                    "core.sshCommand local não é permitido nesta fronteira."
                ),
                "GIT_REMOTE_IDENTITY_URL_REWRITE_NOT_ALLOWED": (
                    "Configuração local url.*.insteadOf não é permitida nesta fronteira."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; inspeção bloqueada."
                ),
                "GIT_EXECUTABLE_CHANGED_DURING_REMOTE_IDENTITY_READ": (
                    "O git.exe mudou durante a inspeção; resultado descartado."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    error,
                    "A identidade Git remota local não pôde ser validada exatamente.",
                ),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                "Identidade Git remota local verificada: "
                f"{evidence['remote_name']} -> {evidence['remote_url']}, "
                f"branch {evidence['branch']} rastreando {evidence['tracking_ref']}; "
                "nenhum contato de rede foi realizado."
            ),
            evidence=evidence,
        )


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


_EXPECTED_GIT_STAGE_NEW_PATH = "_expected_git_stage_new_path"
_EXPECTED_GIT_STAGE_NEW_TARGET_SHA256 = "_expected_git_stage_new_target_sha256"
_EXPECTED_GIT_STAGE_NEW_HEAD_SHA256 = "_expected_git_stage_new_head_sha256"


class GitStageNewFileAction:
    name = "git_stage_new_file"

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
                "O arquivo novo solicitado não existe no checkout atual."
            ),
            "GIT_DIFF_FILE_REQUIRED": (
                "O stage de arquivo novo aceita somente arquivo regular existente."
            ),
            "GIT_DIFF_LINK_NOT_ALLOWED": (
                "Links e junctions não são aceitos nesta fronteira."
            ),
            "GIT_DIFF_PATH_OUTSIDE_REPOSITORY": (
                "O caminho resolvido saiu do checkout fixo."
            ),
            "GIT_STAGE_NEW_TARGET_UNAVAILABLE": (
                "Não foi possível ler o arquivo novo com segurança."
            ),
            "GIT_STAGE_NEW_FILE_TOO_LARGE": (
                "O arquivo novo excede o limite local de 256 KiB."
            ),
            "GIT_STAGE_NEW_BINARY_NOT_ALLOWED": (
                "Arquivo binário não é aceito nesta primeira fronteira para arquivos novos."
            ),
            "GIT_STAGE_NEW_REQUIRES_EMPTY_INDEX": (
                "O M87 exige índice Git vazio antes do stage."
            ),
            "GIT_STAGE_NEW_TARGET_STATUS_FAILED": (
                "Não foi possível confirmar que o arquivo está untracked."
            ),
            "GIT_STAGE_NEW_TARGET_NOT_UNTRACKED": (
                "O M87 aceita somente um arquivo novo ainda não rastreado."
            ),
            "GIT_STAGE_NEW_TARGET_CHANGED_DURING_PREVIEW": (
                "O arquivo novo mudou durante a prévia."
            ),
            "GIT_STAGE_TIMEOUT": "A validação local de stage excedeu o timeout.",
            "GIT_STAGE_NEW_PREFLIGHT_FAILED": (
                "Não foi possível validar o stage do arquivo novo."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o stage Git do arquivo novo.",
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
            evidence = self._git.preview_stage_new_target(raw_path)
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o stage Git do arquivo novo.",
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
                "PREPARAR STAGE GIT DE UM ARQUIVO NOVO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Arquivo novo aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"Tamanho atual: {file_size} byte(s); limite de "
                f"{MAX_GIT_STAGE_NEW_FILE_BYTES} byte(s).\n"
                f"HEAD aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Índice Git atual: vazio; o alvo é um arquivo novo/untracked.\n"
                "Após esta confirmação, THE OS executará somente git add -- <path> "
                "para este arquivo novo aprovado, sem shell. A operação modificará "
                "somente o índice Git; o conteúdo do working tree deve permanecer "
                "inalterado. Se a pós-validação falhar, THE OS pode executar somente "
                "git reset --quiet HEAD -- <path> no mesmo alvo para restaurar o "
                "estado untracked. Nenhum commit, checkout, fetch, pull, push, remote, "
                "revisão ou flag fornecida pelo modelo é autorizada."
            ),
            execution_guard={
                _EXPECTED_GIT_STAGE_NEW_PATH: path,
                _EXPECTED_GIT_STAGE_NEW_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_STAGE_NEW_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = request.arguments.get("path")
        expected_path = request.arguments.get(_EXPECTED_GIT_STAGE_NEW_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_STAGE_NEW_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_STAGE_NEW_HEAD_SHA256
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
                message="O stage de arquivo novo exige a prévia local aprovada.",
                error_code="GIT_STAGE_NEW_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.stage_new_file(
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
                message="Não consegui concluir o stage Git do arquivo novo.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_STAGE_NEW_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_STAGE_NEW_PATH_CHANGED_AFTER_PREVIEW": (
                    "O caminho resolvido mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_NEW_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_NEW_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; stage bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; stage bloqueado."
                ),
                "GIT_STAGE_NEW_REQUIRES_EMPTY_INDEX": (
                    "O índice Git deixou de estar vazio; stage bloqueado."
                ),
                "GIT_STAGE_NEW_TARGET_NOT_UNTRACKED": (
                    "O alvo deixou de ser um arquivo novo/untracked."
                ),
                "GIT_STAGE_NEW_TIMEOUT": (
                    "A operação de stage do arquivo novo excedeu o timeout."
                ),
                "GIT_STAGE_NEW_FAILED": (
                    "A operação de stage Git do arquivo novo falhou."
                ),
                "GIT_STAGE_NEW_POSTCONDITION_FAILED": (
                    "O stage do arquivo novo não atingiu a pós-condição exata e foi revertido quando possível."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "O stage do arquivo novo foi bloqueado."),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Stage Git verificado para arquivo novo {expected_path}: "
                "o índice contém somente esse arquivo como adição e o working tree "
                "permaneceu inalterado."
            ),
            evidence=evidence,
        )



_EXPECTED_GIT_COMMIT_NEW_PATH = "_expected_git_commit_new_path"
_EXPECTED_GIT_COMMIT_NEW_TARGET_SHA256 = "_expected_git_commit_new_target_sha256"
_EXPECTED_GIT_COMMIT_NEW_HEAD_SHA256 = "_expected_git_commit_new_head_sha256"
_EXPECTED_GIT_COMMIT_NEW_MESSAGE = "_expected_git_commit_new_message"


class GitCommitStagedNewFileAction:
    name = "git_commit_staged_new_file"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_COMMIT_NEW_REQUIRES_SINGLE_STAGED_PATH": (
                "O M90 exige exatamente um único arquivo staged no índice."
            ),
            "GIT_COMMIT_NEW_TARGET_NOT_STAGED_ADDITION": (
                "O M90 aceita somente um arquivo novo staged como adição, sem mudança unstaged."
            ),
            "GIT_COMMIT_NEW_TARGET_PREFLIGHT_FAILED": (
                "Não foi possível validar o arquivo novo staged antes do commit."
            ),
            "GIT_COMMIT_NEW_STATE_CHANGED_DURING_PREVIEW": (
                "O estado do índice mudou durante a prévia do commit do arquivo novo."
            ),
            "GIT_STAGE_NEW_TARGET_STATUS_FAILED": (
                "Não foi possível confirmar o estado staged do arquivo novo."
            ),
            "GIT_STAGE_TIMEOUT": "A validação local excedeu o timeout.",
            "GIT_STAGE_PREFLIGHT_FAILED": (
                "Não foi possível validar o índice Git para o commit."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o commit Git local do arquivo novo.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        _ = request
        try:
            evidence = self._git.preview_commit_staged_new_file()
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o commit Git local do arquivo novo.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        target_sha256 = str(evidence["target_sha256"])
        head_sha256 = str(evidence["head_sha"])
        git_path = str(evidence["git_executable_path"])
        git_sha256 = str(evidence["git_executable_sha256"])
        commit_message = str(evidence["commit_message"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "CRIAR COMMIT GIT LOCAL DE UM ARQUIVO NOVO STAGED\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Único arquivo novo staged aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"HEAD pai aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                f"Mensagem fixa do commit: {commit_message}\n"
                "O alvo é um arquivo novo com status staged exato `A ` e sem mudança "
                "unstaged no próprio arquivo.\n"
                "Após esta confirmação, THE OS criará somente um commit Git local "
                "contendo esse único arquivo novo staged. A mensagem não é controlada "
                "pelo modelo. Hooks Git são desabilitados por um hooksPath temporário "
                "vazio e assinatura GPG é desabilitada. Nenhum push, fetch, pull, remote, "
                "checkout, reset, amend, revisão, ref, executável ou flag fornecida pelo "
                "modelo é autorizada. Depois que HEAD avança não há rollback automático "
                "de histórico; qualquer pós-condição inválida bloqueia novas ações."
            ),
            execution_guard={
                _EXPECTED_GIT_COMMIT_NEW_PATH: path,
                _EXPECTED_GIT_COMMIT_NEW_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_COMMIT_NEW_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_COMMIT_NEW_MESSAGE: commit_message,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        expected_path = request.arguments.get(_EXPECTED_GIT_COMMIT_NEW_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_COMMIT_NEW_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_COMMIT_NEW_HEAD_SHA256
        )
        expected_commit_message = request.arguments.get(
            _EXPECTED_GIT_COMMIT_NEW_MESSAGE
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_target_sha256, str)
            or len(expected_target_sha256) != 64
            or not isinstance(expected_head_sha256, str)
            or len(expected_head_sha256) not in {40, 64}
            or not isinstance(expected_commit_message, str)
            or expected_commit_message != FIXED_GIT_COMMIT_NEW_FILE_MESSAGE
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O commit Git de arquivo novo exige a prévia local aprovada.",
                error_code="GIT_COMMIT_NEW_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.commit_staged_new_file(
                expected_path=expected_path,
                expected_target_sha256=expected_target_sha256,
                expected_head_sha256=expected_head_sha256,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
                expected_commit_message=expected_commit_message,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui concluir o commit Git local do arquivo novo.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_COMMIT_NEW_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_COMMIT_NEW_MESSAGE_GUARD_MISMATCH": (
                    "A mensagem fixa aprovada não corresponde mais à política local."
                ),
                "GIT_COMMIT_NEW_PATH_CHANGED_AFTER_PREVIEW": (
                    "O arquivo novo staged mudou após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_NEW_TARGET_CHANGED_AFTER_PREVIEW": (
                    "Os bytes do arquivo novo mudaram após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_NEW_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; commit bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_NEW_TIMEOUT": (
                    "O commit Git local do arquivo novo excedeu o timeout."
                ),
                "GIT_COMMIT_NEW_FAILED": (
                    "O commit Git local do arquivo novo falhou sem avançar HEAD."
                ),
                "GIT_COMMIT_NEW_STATE_AMBIGUOUS_AFTER_FAILURE": (
                    "O processo de commit falhou, mas HEAD mudou; o estado precisa de inspeção antes de qualquer nova mutação."
                ),
                "GIT_COMMIT_NEW_POSTCONDITION_FAILED": (
                    "O commit avançou, mas a pós-condição do arquivo novo não pôde ser comprovada; não houve rollback automático de histórico."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    error,
                    "O commit Git local do arquivo novo foi bloqueado.",
                ),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Commit Git local verificado para arquivo novo {expected_path}: "
                f"{evidence['commit_sha']}; um único arquivo agora rastreado, "
                "índice vazio e sem operação remota."
            ),
            evidence=evidence,
        )



_EXPECTED_GIT_COMMIT_PATH = "_expected_git_commit_path"
_EXPECTED_GIT_COMMIT_TARGET_SHA256 = "_expected_git_commit_target_sha256"
_EXPECTED_GIT_COMMIT_HEAD_SHA256 = "_expected_git_commit_head_sha256"
_EXPECTED_GIT_COMMIT_MESSAGE = "_expected_git_commit_message"


class GitCommitStagedFileAction:
    name = "git_commit_staged_file"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, git: WindowsLocalGitAdapter) -> None:
        self._git = git

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        messages = {
            "GIT_COMMIT_REQUIRES_SINGLE_STAGED_PATH": (
                "O M89 exige exatamente um único arquivo staged no índice."
            ),
            "GIT_COMMIT_TARGET_NOT_STAGED_TRACKED_MODIFICATION": (
                "O M89 aceita somente uma modificação rastreada staged, sem mudança unstaged."
            ),
            "GIT_COMMIT_TARGET_PREFLIGHT_FAILED": (
                "Não foi possível validar o arquivo staged antes do commit."
            ),
            "GIT_COMMIT_STATE_CHANGED_DURING_PREVIEW": (
                "O estado do índice mudou durante a prévia do commit."
            ),
            "GIT_STAGE_TIMEOUT": "A validação local excedeu o timeout.",
            "GIT_STAGE_PREFLIGHT_FAILED": (
                "Não foi possível validar o índice Git para o commit."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o commit Git local.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        _ = request
        try:
            evidence = self._git.preview_commit_staged_file()
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o commit Git local.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        target_sha256 = str(evidence["target_sha256"])
        head_sha256 = str(evidence["head_sha"])
        git_path = str(evidence["git_executable_path"])
        git_sha256 = str(evidence["git_executable_sha256"])
        commit_message = str(evidence["commit_message"])

        return ConfirmationPreview(
            allowed=True,
            text=(
                "CRIAR COMMIT GIT LOCAL DE UM ARQUIVO STAGED\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Único arquivo staged aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"HEAD pai aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                f"Mensagem fixa do commit: {commit_message}\n"
                "O alvo é uma modificação já rastreada com status staged exato `M ` "
                "e sem mudança unstaged no próprio arquivo.\n"
                "Após esta confirmação, THE OS criará somente um commit Git local "
                "contendo esse único arquivo staged. A mensagem não é controlada pelo "
                "modelo. Hooks Git são desabilitados por um hooksPath temporário vazio "
                "e assinatura GPG é desabilitada. Nenhum push, fetch, pull, remote, "
                "checkout, reset, amend, revisão, ref, executável ou flag fornecida pelo "
                "modelo é autorizada. Depois que HEAD avança não há rollback automático "
                "de histórico; qualquer pós-condição inválida bloqueia novas ações."
            ),
            execution_guard={
                _EXPECTED_GIT_COMMIT_PATH: path,
                _EXPECTED_GIT_COMMIT_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_COMMIT_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_COMMIT_MESSAGE: commit_message,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        expected_path = request.arguments.get(_EXPECTED_GIT_COMMIT_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_COMMIT_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_COMMIT_HEAD_SHA256
        )
        expected_commit_message = request.arguments.get(
            _EXPECTED_GIT_COMMIT_MESSAGE
        )
        expected_git_path = request.arguments.get(_EXPECTED_GIT_EXECUTABLE_PATH)
        expected_git_sha256 = request.arguments.get(
            _EXPECTED_GIT_EXECUTABLE_SHA256
        )

        if (
            not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_target_sha256, str)
            or len(expected_target_sha256) != 64
            or not isinstance(expected_head_sha256, str)
            or len(expected_head_sha256) not in {40, 64}
            or not isinstance(expected_commit_message, str)
            or expected_commit_message != FIXED_GIT_COMMIT_MESSAGE
            or not isinstance(expected_git_path, str)
            or not expected_git_path
            or not isinstance(expected_git_sha256, str)
            or len(expected_git_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O commit Git exige a prévia local aprovada.",
                error_code="GIT_COMMIT_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.commit_staged_file(
                expected_path=expected_path,
                expected_target_sha256=expected_target_sha256,
                expected_head_sha256=expected_head_sha256,
                expected_git_executable_path=expected_git_path,
                expected_git_executable_sha256=expected_git_sha256,
                expected_commit_message=expected_commit_message,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui concluir o commit Git local.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_COMMIT_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_COMMIT_MESSAGE_GUARD_MISMATCH": (
                    "A mensagem fixa aprovada não corresponde mais à política local."
                ),
                "GIT_COMMIT_PATH_CHANGED_AFTER_PREVIEW": (
                    "O arquivo staged mudou após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_TARGET_CHANGED_AFTER_PREVIEW": (
                    "Os bytes do arquivo mudaram após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; commit bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; commit bloqueado."
                ),
                "GIT_COMMIT_TIMEOUT": "O commit Git local excedeu o timeout.",
                "GIT_COMMIT_FAILED": "O commit Git local falhou sem avançar HEAD.",
                "GIT_COMMIT_STATE_AMBIGUOUS_AFTER_FAILURE": (
                    "O processo de commit falhou, mas HEAD mudou; o estado precisa de inspeção antes de qualquer nova mutação."
                ),
                "GIT_COMMIT_POSTCONDITION_FAILED": (
                    "O commit avançou, mas a pós-condição exata não pôde ser comprovada; não houve rollback automático de histórico."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "O commit Git local foi bloqueado."),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Commit Git local verificado para {expected_path}: "
                f"{evidence['commit_sha']}; um único arquivo, índice vazio e sem operação remota."
            ),
            evidence=evidence,
        )



_EXPECTED_GIT_UNSTAGE_NEW_PATH = "_expected_git_unstage_new_path"
_EXPECTED_GIT_UNSTAGE_NEW_TARGET_SHA256 = "_expected_git_unstage_new_target_sha256"
_EXPECTED_GIT_UNSTAGE_NEW_HEAD_SHA256 = "_expected_git_unstage_new_head_sha256"


class GitUnstageNewFileAction:
    name = "git_unstage_new_file"

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
                "O arquivo novo solicitado não existe no checkout atual."
            ),
            "GIT_DIFF_FILE_REQUIRED": (
                "O unstage de arquivo novo aceita somente arquivo regular existente."
            ),
            "GIT_DIFF_LINK_NOT_ALLOWED": (
                "Links e junctions não são aceitos nesta fronteira."
            ),
            "GIT_DIFF_PATH_OUTSIDE_REPOSITORY": (
                "O caminho resolvido saiu do checkout fixo."
            ),
            "GIT_STAGE_NEW_TARGET_UNAVAILABLE": (
                "Não foi possível ler o arquivo novo com segurança."
            ),
            "GIT_STAGE_NEW_FILE_TOO_LARGE": (
                "O arquivo novo excede o limite local de 256 KiB."
            ),
            "GIT_STAGE_NEW_BINARY_NOT_ALLOWED": (
                "Arquivo binário não é aceito nesta fronteira."
            ),
            "GIT_UNSTAGE_NEW_REQUIRES_ONLY_TARGET_STAGED": (
                "O M88 exige que o índice contenha somente o arquivo novo solicitado."
            ),
            "GIT_STAGE_NEW_TARGET_STATUS_FAILED": (
                "Não foi possível confirmar o estado staged do arquivo novo."
            ),
            "GIT_UNSTAGE_NEW_TARGET_NOT_STAGED_ADDITION": (
                "O M88 aceita somente um arquivo novo staged como adição, sem mudança unstaged."
            ),
            "GIT_STAGE_NEW_TARGET_CHANGED_DURING_PREVIEW": (
                "O arquivo novo mudou durante a prévia."
            ),
            "GIT_STAGE_TIMEOUT": "A validação local excedeu o timeout.",
            "GIT_UNSTAGE_NEW_PREFLIGHT_FAILED": (
                "Não foi possível validar o unstage do arquivo novo."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(evidence.get("error")),
                "Não foi possível preparar o unstage Git do arquivo novo.",
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
            evidence = self._git.preview_unstage_new_target(raw_path)
        except (OSError, RuntimeError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar o unstage Git do arquivo novo.",
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
                "REMOVER STAGE GIT DE UM ARQUIVO NOVO\n"
                f"Repositório fixo: {evidence['repository_root']}\n"
                f"Arquivo novo aprovado: {path}\n"
                f"SHA-256 atual do arquivo: {target_sha256}\n"
                f"Tamanho atual: {file_size} byte(s); limite de "
                f"{MAX_GIT_STAGE_NEW_FILE_BYTES} byte(s).\n"
                f"HEAD aprovado: {head_sha256}\n"
                f"git.exe aprovado: {git_path}\n"
                f"SHA-256 do git.exe: {git_sha256}\n"
                "Índice Git atual: contém somente esse arquivo como nova adição staged, "
                "sem mudança unstaged no alvo.\n"
                "Após esta confirmação, THE OS executará somente "
                "git reset --quiet HEAD -- <path> para este arquivo novo aprovado, "
                "sem shell. A operação modificará somente o índice Git; o conteúdo do "
                "working tree deve permanecer inalterado e o alvo deve voltar a untracked. "
                "Se a pós-validação falhar, THE OS pode executar somente git add -- <path> "
                "no mesmo alvo para restaurar o stage anterior. Nenhum commit, checkout, "
                "fetch, pull, push, remote, revisão ou flag fornecida pelo modelo é autorizada."
            ),
            execution_guard={
                _EXPECTED_GIT_UNSTAGE_NEW_PATH: path,
                _EXPECTED_GIT_UNSTAGE_NEW_TARGET_SHA256: target_sha256,
                _EXPECTED_GIT_UNSTAGE_NEW_HEAD_SHA256: head_sha256,
                _EXPECTED_GIT_EXECUTABLE_PATH: git_path,
                _EXPECTED_GIT_EXECUTABLE_SHA256: git_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = request.arguments.get("path")
        expected_path = request.arguments.get(_EXPECTED_GIT_UNSTAGE_NEW_PATH)
        expected_target_sha256 = request.arguments.get(
            _EXPECTED_GIT_UNSTAGE_NEW_TARGET_SHA256
        )
        expected_head_sha256 = request.arguments.get(
            _EXPECTED_GIT_UNSTAGE_NEW_HEAD_SHA256
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
                message="O unstage de arquivo novo exige a prévia local aprovada.",
                error_code="GIT_UNSTAGE_NEW_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._git.unstage_new_file(
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
                message="Não consegui concluir o unstage Git do arquivo novo.",
                evidence={"exception": type(exc).__name__},
                error_code="GIT_UNSTAGE_NEW_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "GIT_UNSTAGE_NEW_PATH_CHANGED_AFTER_PREVIEW": (
                    "O caminho resolvido mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_NEW_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_NEW_HEAD_CHANGED_AFTER_PREVIEW": (
                    "O HEAD mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW": (
                    "O git.exe mudou após a aprovação; unstage bloqueado."
                ),
                "GIT_UNSTAGE_NEW_REQUIRES_ONLY_TARGET_STAGED": (
                    "O índice Git deixou de conter somente o arquivo novo aprovado."
                ),
                "GIT_UNSTAGE_NEW_TARGET_NOT_STAGED_ADDITION": (
                    "O alvo deixou de ser uma adição staged limpa."
                ),
                "GIT_UNSTAGE_NEW_TIMEOUT": (
                    "A operação de unstage do arquivo novo excedeu o timeout."
                ),
                "GIT_UNSTAGE_NEW_FAILED": (
                    "A operação de unstage Git do arquivo novo falhou."
                ),
                "GIT_UNSTAGE_NEW_POSTCONDITION_FAILED": (
                    "O unstage do arquivo novo não atingiu a pós-condição exata e o stage anterior foi restaurado quando possível."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    error,
                    "O unstage do arquivo novo foi bloqueado.",
                ),
                evidence=evidence,
                error_code=error,
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Unstage Git verificado para arquivo novo {expected_path}: "
                "o índice ficou vazio, o alvo voltou a untracked e o working tree "
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
