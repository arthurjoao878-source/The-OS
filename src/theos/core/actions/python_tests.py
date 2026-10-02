from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.python_tests import (
    MAX_PROJECT_PYTHON_FILES,
    MAX_PROJECT_PYTHON_TOTAL_BYTES,
    MAX_PYTHON_UNIT_TEST_FILE_BYTES,
    PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
    WindowsPythonUnitTestAdapter,
)

_EXPECTED_TEST_PATH = "_expected_test_path"
_EXPECTED_TEST_SHA256 = "_expected_test_sha256"
_EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256 = (
    "_expected_project_python_manifest_sha256"
)


class RunPythonUnitTestFileAction:
    name = "run_python_unit_test_file"
    risk = ActionRisk.PRIVILEGED

    def __init__(self, adapter: WindowsPythonUnitTestAdapter) -> None:
        self._adapter = adapter

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        error = evidence.get("error")
        messages = {
            "PATH_REQUIRED": "O caminho do teste está vazio.",
            "PATH_NOT_FOUND": "O arquivo de teste não existe.",
            "PATH_NOT_FILE": "O caminho selecionado não é um arquivo.",
            "LINK_TARGET_NOT_ALLOWED": (
                "Links e junctions não são aceitos para execução de testes."
            ),
            "TEST_TARGET_OUTSIDE_UNIT_ROOT": (
                "O teste precisa estar dentro de tests/unit do checkout atual."
            ),
            "UNIT_TEST_FILE_REQUIRED": (
                "A execução aceita somente tests/unit/test_*.py."
            ),
            "FILE_TOO_LARGE": (
                "O arquivo de teste excede o limite local de 256 KiB."
            ),
            "PROJECT_PYTHON_ROOT_UNAVAILABLE": (
                "Os roots Python fixos do projeto não estão disponíveis."
            ),
            "PROJECT_PYTHON_LINK_NOT_ALLOWED": (
                "O manifesto Python do projeto encontrou link/junction e foi bloqueado."
            ),
            "PROJECT_PYTHON_STATE_UNAVAILABLE": (
                "Não foi possível hashear o estado Python do projeto com segurança."
            ),
            "PROJECT_PYTHON_FILE_TOO_LARGE": (
                "Um arquivo Python do manifesto excede o limite local de 256 KiB."
            ),
            "PROJECT_PYTHON_TOTAL_TOO_LARGE": (
                "O manifesto Python do projeto excede o limite total local."
            ),
            "PROJECT_PYTHON_FILE_COUNT_EXCEEDED": (
                "O manifesto Python do projeto excede o limite local de arquivos."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(error),
                "Não foi possível preparar com segurança a execução do teste.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_path = str(request.arguments.get("path", "")).strip()
        if not raw_path:
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: caminho vazio.",
            )

        try:
            evidence = self._adapter.preview_test_target(raw_path)
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar com segurança a execução do teste.",
            )

        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        path = str(evidence["path"])
        sha256 = str(evidence["sha256"])
        project_manifest_sha256 = str(
            evidence["project_python_manifest_sha256"]
        )
        project_file_count = int(evidence["project_python_file_count"])
        project_total_bytes = int(evidence["project_python_total_bytes"])
        return ConfirmationPreview(
            allowed=True,
            text=(
                "EXECUTAR UM ARQUIVO DE TESTE PYTHON\n"
                f"Caminho aprovado: {path}\n"
                f"SHA-256 aprovado: {sha256}\n"
                "Manifesto Python do projeto: src/theos + tests/unit\n"
                f"Manifesto SHA-256 aprovado: {project_manifest_sha256}\n"
                f"Manifesto: {project_file_count} arquivo(s), "
                f"{project_total_bytes} byte(s); limites de "
                f"{MAX_PROJECT_PYTHON_FILES} arquivo(s) e "
                f"{MAX_PROJECT_PYTHON_TOTAL_BYTES} byte(s) totais.\n"
                f"Limite do arquivo: {MAX_PYTHON_UNIT_TEST_FILE_BYTES} byte(s).\n"
                f"Timeout: {PYTHON_UNIT_TEST_TIMEOUT_SECONDS:g}s.\n"
                "RISCO PRIVILEGIADO: pytest executará código Python do arquivo de teste "
                "e dos módulos que ele importar com as permissões do usuário atual. "
                "THE OS NÃO fornece sandbox para esses efeitos externos.\n"
                "A seleção é estreita: somente este tests/unit/test_*.py explícito. "
                "THE OS usa somente pytest.exe do mesmo venv, argv fixo, sem shell, "
                "sem plugin autoload, sem conftest, sem cacheprovider e sem bytecode. "
                "A configuração pytest implícita desabilitada é substituída por config "
                "temporário vazio e rootdir fixo; PYTEST_ADDOPTS/PYTEST_PLUGINS herdados removidos. "
                "Variáveis PYTHON* herdadas são removidas; o child recebe "
                "PYTHONDONTWRITEBYTECODE=1, PYTHONNOUSERSITE=1 e PYTHONSAFEPATH=1. "
                "Isso não torna imports herméticos: o venv/site-packages continua parte "
                "da execução privilegiada. stdout/stderr brutos não são enviados ao modelo. Em falha/erro, "
                "o JUnit temporário pode fornecer até 3 diagnósticos estruturados e "
                "limitados; o corpo de traceback do XML não é devolvido."
            ),
            execution_guard={
                _EXPECTED_TEST_PATH: path,
                _EXPECTED_TEST_SHA256: sha256,
                _EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256: (
                    project_manifest_sha256
                ),
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        expected_path = request.arguments.get(_EXPECTED_TEST_PATH)
        expected_sha256 = request.arguments.get(_EXPECTED_TEST_SHA256)
        expected_project_manifest_sha256 = request.arguments.get(
            _EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256
        )
        if (
            not raw_path
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or not isinstance(expected_project_manifest_sha256, str)
            or len(expected_project_manifest_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A execução do teste exige a prévia local aprovada.",
                error_code="PYTEST_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._adapter.run_test_file(
                raw_path,
                expected_path=expected_path,
                expected_sha256=expected_sha256,
                expected_project_python_manifest_sha256=(
                    expected_project_manifest_sha256
                ),
            )
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui executar o teste Python controlado.",
                evidence={"exception": type(exc).__name__},
                error_code="PYTEST_EXECUTION_FAILED",
            )

        error = evidence.get("error")
        if isinstance(error, str):
            messages = {
                "PATH_NOT_FOUND": "O arquivo de teste não existe mais.",
                "PATH_NOT_FILE": "O alvo deixou de ser um arquivo.",
                "LINK_TARGET_NOT_ALLOWED": (
                    "O alvo passou a ser link/junction e foi bloqueado."
                ),
                "TEST_TARGET_OUTSIDE_UNIT_ROOT": (
                    "O alvo deixou a raiz tests/unit permitida."
                ),
                "UNIT_TEST_FILE_REQUIRED": (
                    "O alvo não corresponde mais a tests/unit/test_*.py."
                ),
                "FILE_TOO_LARGE": "O arquivo de teste excede o limite local.",
                "TEST_TARGET_CHANGED_AFTER_PREVIEW": (
                    "O arquivo de teste mudou após a aprovação; execução bloqueada."
                ),
                "PROJECT_PYTHON_ROOT_UNAVAILABLE": (
                    "Os roots Python fixos do projeto deixaram de estar disponíveis."
                ),
                "PROJECT_PYTHON_LINK_NOT_ALLOWED": (
                    "O estado Python do projeto contém link/junction e foi bloqueado."
                ),
                "PROJECT_PYTHON_STATE_UNAVAILABLE": (
                    "Não foi possível validar o estado Python do projeto."
                ),
                "PROJECT_PYTHON_FILE_TOO_LARGE": (
                    "Um arquivo Python do projeto excede o limite do manifesto."
                ),
                "PROJECT_PYTHON_TOTAL_TOO_LARGE": (
                    "O estado Python do projeto excede o limite total do manifesto."
                ),
                "PROJECT_PYTHON_FILE_COUNT_EXCEEDED": (
                    "O estado Python do projeto excede o limite de arquivos."
                ),
                "PROJECT_PYTHON_STATE_CHANGED_AFTER_PREVIEW": (
                    "O estado Python do projeto mudou após a aprovação; "
                    "pytest não foi iniciado."
                ),
                "PYTEST_VERIFIER_NOT_AVAILABLE": (
                    "O pytest.exe controlado do venv não está disponível."
                ),
                "PYTEST_TIMEOUT": "O teste excedeu o timeout local de 30 segundos.",
                "TEST_TARGET_CHANGED_DURING_RUN": (
                    "O arquivo de teste mudou durante a execução; resultado descartado."
                ),
                "PROJECT_PYTHON_STATE_INVALID_AFTER_RUN": (
                    "O estado Python do projeto ficou inválido durante o pytest; "
                    "resultado descartado."
                ),
                "PROJECT_PYTHON_STATE_CHANGED_DURING_RUN": (
                    "O estado Python do projeto mudou durante o pytest; "
                    "resultado descartado."
                ),
                "PYTEST_PROCESS_FAILED": (
                    "O processo pytest terminou com falha operacional."
                ),
                "PYTEST_REPORT_MISSING": (
                    "O pytest não produziu o relatório estrutural esperado."
                ),
                "PYTEST_REPORT_TOO_LARGE": (
                    "O relatório pytest excedeu o limite local."
                ),
                "PYTEST_REPORT_INVALID": (
                    "O relatório estrutural do pytest é inválido."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(error, "A execução de teste foi bloqueada."),
                evidence=evidence,
                error_code=error,
            )

        path = Path(str(evidence["path"]))
        tests_run = int(evidence.get("tests_run", 0))
        failures = int(evidence.get("failures", 0))
        errors = int(evidence.get("errors", 0))
        skipped = int(evidence.get("skipped", 0))
        if bool(evidence.get("passed")):
            message = (
                f"Teste unitário controlado passou em {path.name}: "
                f"{tests_run} teste(s), {skipped} ignorado(s)."
            )
        elif bool(evidence.get("no_tests_collected")):
            message = (
                f"Execução controlada concluída em {path.name}, "
                "mas nenhum teste foi coletado."
            )
        else:
            diagnostics = evidence.get("failure_diagnostics", [])
            diagnostic_count = len(diagnostics) if isinstance(diagnostics, list) else 0
            message = (
                f"Teste unitário controlado concluiu com falha em {path.name}: "
                f"{failures} falha(s), {errors} erro(s), "
                f"{tests_run} teste(s) executado(s); "
                f"{diagnostic_count} diagnóstico(s) limitado(s) disponível(is)."
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )
