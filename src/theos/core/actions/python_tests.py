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
    MAX_PYTEST_FAILURE_DIAGNOSTICS,
    MAX_PYTEST_PACKAGE_FILES,
    MAX_PYTEST_PACKAGE_TOTAL_BYTES,
    MAX_PYTEST_VERIFIER_BYTES,
    MAX_PYTHON_RUNTIME_EXE_BYTES,
    MAX_PYTHON_UNIT_TEST_FILE_BYTES,
    MAX_PYTHON_UNIT_TEST_MANY_FILES,
    MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES,
    MAX_PYVENV_CONFIG_BYTES,
    MIN_PYTHON_UNIT_TEST_MANY_FILES,
    PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
    WindowsPythonUnitTestAdapter,
)

_EXPECTED_TEST_PATH = "_expected_test_path"
_EXPECTED_TEST_SHA256 = "_expected_test_sha256"
_EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256 = (
    "_expected_project_python_manifest_sha256"
)
_EXPECTED_PYTEST_VERIFIER_PATH = "_expected_pytest_verifier_path"
_EXPECTED_PYTEST_VERIFIER_SHA256 = "_expected_pytest_verifier_sha256"
_EXPECTED_PYTEST_PACKAGE_MANIFEST_SHA256 = (
    "_expected_pytest_package_manifest_sha256"
)
_EXPECTED_PYTHON_RUNTIME_STATE_SHA256 = (
    "_expected_python_runtime_state_sha256"
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
            "PYTEST_VERIFIER_NOT_AVAILABLE": (
                "O pytest.exe controlado do venv não está disponível."
            ),
            "PYTEST_VERIFIER_LINK_NOT_ALLOWED": (
                "O pytest.exe controlado não pode ser link/junction."
            ),
            "PYTEST_VERIFIER_TOO_LARGE": (
                "O pytest.exe controlado excede o limite local."
            ),
            "PYTEST_VERIFIER_UNREADABLE": (
                "Não foi possível hashear o pytest.exe controlado."
            ),
            "PYTEST_PACKAGE_ROOT_UNAVAILABLE": (
                "Os roots pytest/_pytest do venv não estão disponíveis."
            ),
            "PYTEST_PACKAGE_LINK_NOT_ALLOWED": (
                "O estado pytest/_pytest contém link/junction e foi bloqueado."
            ),
            "PYTEST_PACKAGE_STATE_UNAVAILABLE": (
                "Não foi possível hashear o estado pytest/_pytest."
            ),
            "PYTEST_PACKAGE_FILE_TOO_LARGE": (
                "Um arquivo pytest/_pytest excede o limite local."
            ),
            "PYTEST_PACKAGE_TOTAL_TOO_LARGE": (
                "O estado pytest/_pytest excede o limite total local."
            ),
            "PYTEST_PACKAGE_FILE_COUNT_EXCEEDED": (
                "O estado pytest/_pytest excede o limite local de arquivos."
            ),
            "PYTHON_RUNTIME_NOT_AVAILABLE": (
                "O Scripts/python.exe do venv não está disponível."
            ),
            "PYTHON_RUNTIME_LINK_NOT_ALLOWED": (
                "O Scripts/python.exe do venv não pode ser link/junction."
            ),
            "PYTHON_RUNTIME_TOO_LARGE": (
                "O Scripts/python.exe do venv excede o limite local."
            ),
            "PYVENV_CONFIG_NOT_AVAILABLE": (
                "O pyvenv.cfg do venv não está disponível."
            ),
            "PYVENV_CONFIG_LINK_NOT_ALLOWED": (
                "O pyvenv.cfg do venv não pode ser link/junction."
            ),
            "PYVENV_CONFIG_TOO_LARGE": (
                "O pyvenv.cfg do venv excede o limite local."
            ),
            "PYTHON_RUNTIME_STATE_UNREADABLE": (
                "Não foi possível hashear o bootstrap Python do venv."
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

        try:
            verifier = self._adapter.preview_pytest_verifier()
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível validar o pytest.exe controlado.",
            )
        if verifier.get("error") is not None:
            return self._blocked_preview(verifier)

        try:
            package_state = self._adapter.preview_pytest_package_state()
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível validar o estado pytest/_pytest.",
            )
        if package_state.get("error") is not None:
            return self._blocked_preview(package_state)

        try:
            runtime_state = self._adapter.preview_python_runtime_state()
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível validar o bootstrap Python do venv.",
            )
        if runtime_state.get("error") is not None:
            return self._blocked_preview(runtime_state)

        path = str(evidence["path"])
        sha256 = str(evidence["sha256"])
        project_manifest_sha256 = str(
            evidence["project_python_manifest_sha256"]
        )
        project_file_count = int(evidence["project_python_file_count"])
        project_total_bytes = int(evidence["project_python_total_bytes"])
        pytest_verifier_path = str(verifier["pytest_verifier_path"])
        pytest_verifier_sha256 = str(verifier["pytest_verifier_sha256"])
        pytest_verifier_size_bytes = int(verifier["pytest_verifier_size_bytes"])
        pytest_package_manifest_sha256 = str(
            package_state["pytest_package_manifest_sha256"]
        )
        pytest_package_file_count = int(
            package_state["pytest_package_file_count"]
        )
        pytest_package_total_bytes = int(
            package_state["pytest_package_total_bytes"]
        )
        python_runtime_path = str(runtime_state["python_runtime_path"])
        python_runtime_sha256 = str(runtime_state["python_runtime_sha256"])
        python_runtime_size_bytes = int(
            runtime_state["python_runtime_size_bytes"]
        )
        pyvenv_config_path = str(runtime_state["pyvenv_config_path"])
        pyvenv_config_sha256 = str(runtime_state["pyvenv_config_sha256"])
        pyvenv_config_size_bytes = int(
            runtime_state["pyvenv_config_size_bytes"]
        )
        python_runtime_state_sha256 = str(
            runtime_state["python_runtime_state_sha256"]
        )
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
                f"pytest.exe aprovado: {pytest_verifier_path}\n"
                f"SHA-256 do pytest.exe: {pytest_verifier_sha256}\n"
                f"pytest.exe: {pytest_verifier_size_bytes} byte(s); limite de "
                f"{MAX_PYTEST_VERIFIER_BYTES} byte(s).\n"
                "Manifesto pytest/_pytest do venv: pytest + _pytest\n"
                f"Manifesto pytest/_pytest SHA-256: "
                f"{pytest_package_manifest_sha256}\n"
                f"Manifesto pytest/_pytest: {pytest_package_file_count} arquivo(s), "
                f"{pytest_package_total_bytes} byte(s); limites de "
                f"{MAX_PYTEST_PACKAGE_FILES} arquivo(s) e "
                f"{MAX_PYTEST_PACKAGE_TOTAL_BYTES} byte(s) totais.\n"
                "Estado bootstrap Python do venv: Scripts/python.exe + pyvenv.cfg\n"
                f"Scripts/python.exe aprovado: {python_runtime_path}\n"
                f"SHA-256 do Scripts/python.exe: {python_runtime_sha256}\n"
                f"Scripts/python.exe: {python_runtime_size_bytes} byte(s); limite de "
                f"{MAX_PYTHON_RUNTIME_EXE_BYTES} byte(s).\n"
                f"pyvenv.cfg aprovado: {pyvenv_config_path}\n"
                f"SHA-256 do pyvenv.cfg: {pyvenv_config_sha256}\n"
                f"pyvenv.cfg: {pyvenv_config_size_bytes} byte(s); limite de "
                f"{MAX_PYVENV_CONFIG_BYTES} byte(s).\n"
                f"Estado bootstrap Python SHA-256: {python_runtime_state_sha256}\n"
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
                "O estado dos roots pytest/_pytest é vinculado à aprovação e "
                "revalidado antes/depois, mas não é dependency closure do venv. "
                "Scripts/python.exe + pyvenv.cfg também ficam vinculados e revalidados, "
                "mas isso não é runtime dependency closure. "
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
                _EXPECTED_PYTEST_VERIFIER_PATH: pytest_verifier_path,
                _EXPECTED_PYTEST_VERIFIER_SHA256: pytest_verifier_sha256,
                _EXPECTED_PYTEST_PACKAGE_MANIFEST_SHA256: (
                    pytest_package_manifest_sha256
                ),
                _EXPECTED_PYTHON_RUNTIME_STATE_SHA256: (
                    python_runtime_state_sha256
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
        expected_pytest_verifier_path = request.arguments.get(
            _EXPECTED_PYTEST_VERIFIER_PATH
        )
        expected_pytest_verifier_sha256 = request.arguments.get(
            _EXPECTED_PYTEST_VERIFIER_SHA256
        )
        expected_pytest_package_manifest_sha256 = request.arguments.get(
            _EXPECTED_PYTEST_PACKAGE_MANIFEST_SHA256
        )
        expected_python_runtime_state_sha256 = request.arguments.get(
            _EXPECTED_PYTHON_RUNTIME_STATE_SHA256
        )
        if (
            not raw_path
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or not isinstance(expected_project_manifest_sha256, str)
            or len(expected_project_manifest_sha256) != 64
            or not isinstance(expected_pytest_verifier_path, str)
            or not expected_pytest_verifier_path
            or not isinstance(expected_pytest_verifier_sha256, str)
            or len(expected_pytest_verifier_sha256) != 64
            or not isinstance(expected_pytest_package_manifest_sha256, str)
            or len(expected_pytest_package_manifest_sha256) != 64
            or not isinstance(expected_python_runtime_state_sha256, str)
            or len(expected_python_runtime_state_sha256) != 64
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
                expected_pytest_verifier_path=expected_pytest_verifier_path,
                expected_pytest_verifier_sha256=(
                    expected_pytest_verifier_sha256
                ),
                expected_pytest_package_manifest_sha256=(
                    expected_pytest_package_manifest_sha256
                ),
                expected_python_runtime_state_sha256=(
                    expected_python_runtime_state_sha256
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
                "PYTEST_VERIFIER_LINK_NOT_ALLOWED": (
                    "O pytest.exe controlado virou link/junction e foi bloqueado."
                ),
                "PYTEST_VERIFIER_TOO_LARGE": (
                    "O pytest.exe controlado excede o limite local."
                ),
                "PYTEST_VERIFIER_UNREADABLE": (
                    "Não foi possível validar o pytest.exe controlado."
                ),
                "PYTEST_VERIFIER_CHANGED_AFTER_PREVIEW": (
                    "O pytest.exe controlado mudou após a aprovação; execução bloqueada."
                ),
                "PYTEST_PACKAGE_ROOT_UNAVAILABLE": (
                    "Os roots pytest/_pytest deixaram de estar disponíveis."
                ),
                "PYTEST_PACKAGE_LINK_NOT_ALLOWED": (
                    "O estado pytest/_pytest contém link/junction e foi bloqueado."
                ),
                "PYTEST_PACKAGE_STATE_UNAVAILABLE": (
                    "Não foi possível validar o estado pytest/_pytest."
                ),
                "PYTEST_PACKAGE_FILE_TOO_LARGE": (
                    "Um arquivo pytest/_pytest excede o limite do manifesto."
                ),
                "PYTEST_PACKAGE_TOTAL_TOO_LARGE": (
                    "O estado pytest/_pytest excede o limite total do manifesto."
                ),
                "PYTEST_PACKAGE_FILE_COUNT_EXCEEDED": (
                    "O estado pytest/_pytest excede o limite de arquivos."
                ),
                "PYTEST_PACKAGE_STATE_CHANGED_AFTER_PREVIEW": (
                    "O estado pytest/_pytest mudou após a aprovação; "
                    "pytest não foi iniciado."
                ),
                "PYTHON_RUNTIME_NOT_AVAILABLE": (
                    "O Scripts/python.exe do venv não está disponível."
                ),
                "PYTHON_RUNTIME_LINK_NOT_ALLOWED": (
                    "O Scripts/python.exe do venv virou link/junction e foi bloqueado."
                ),
                "PYTHON_RUNTIME_TOO_LARGE": (
                    "O Scripts/python.exe do venv excede o limite local."
                ),
                "PYVENV_CONFIG_NOT_AVAILABLE": (
                    "O pyvenv.cfg do venv não está disponível."
                ),
                "PYVENV_CONFIG_LINK_NOT_ALLOWED": (
                    "O pyvenv.cfg do venv virou link/junction e foi bloqueado."
                ),
                "PYVENV_CONFIG_TOO_LARGE": (
                    "O pyvenv.cfg do venv excede o limite local."
                ),
                "PYTHON_RUNTIME_STATE_UNREADABLE": (
                    "Não foi possível validar o bootstrap Python do venv."
                ),
                "PYTHON_RUNTIME_STATE_CHANGED_AFTER_PREVIEW": (
                    "O bootstrap Python do venv mudou após a aprovação; "
                    "pytest não foi iniciado."
                ),
                "PYTEST_TIMEOUT": "O teste excedeu o timeout local de 30 segundos.",
                "PYTEST_VERIFIER_CHANGED_DURING_RUN": (
                    "O pytest.exe controlado mudou durante a execução; resultado descartado."
                ),
                "PYTEST_PACKAGE_STATE_CHANGED_DURING_RUN": (
                    "O estado pytest/_pytest mudou durante a execução; resultado descartado."
                ),
                "PYTHON_RUNTIME_STATE_CHANGED_DURING_RUN": (
                    "O bootstrap Python do venv mudou durante a execução; resultado descartado."
                ),
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

_EXPECTED_TEST_BATCH_TARGETS = "_expected_test_batch_targets"


class RunPythonUnitTestFilesAction:
    name = "run_python_unit_test_files"
    risk = ActionRisk.PRIVILEGED

    def __init__(self, adapter: WindowsPythonUnitTestAdapter) -> None:
        self._adapter = adapter

    @staticmethod
    def _blocked_preview(evidence: dict[str, object]) -> ConfirmationPreview:
        error = evidence.get("error")
        messages = {
            "TEST_BATCH_FILE_COUNT_OUT_OF_RANGE": (
                "O lote precisa conter entre 2 e 4 arquivos de teste explícitos."
            ),
            "PATH_REQUIRED": "Um caminho de teste está vazio.",
            "PATH_NOT_FOUND": "Um arquivo de teste do lote não existe.",
            "PATH_NOT_FILE": "Um alvo do lote não é arquivo.",
            "LINK_TARGET_NOT_ALLOWED": (
                "Links e junctions não são aceitos no lote de testes."
            ),
            "TEST_TARGET_OUTSIDE_UNIT_ROOT": (
                "Todos os testes precisam estar em tests/unit do checkout atual."
            ),
            "UNIT_TEST_FILE_REQUIRED": (
                "O lote aceita somente tests/unit/test_*.py."
            ),
            "FILE_TOO_LARGE": (
                "Um arquivo de teste excede o limite local de 256 KiB."
            ),
            "DUPLICATE_RESOLVED_TARGET": (
                "O lote contém caminhos que resolvem para o mesmo arquivo."
            ),
            "TEST_BATCH_TOTAL_BYTES_TOO_LARGE": (
                "O lote de testes excede o limite total local de 768 KiB."
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
                "Um arquivo Python do manifesto excede o limite local."
            ),
            "PROJECT_PYTHON_TOTAL_TOO_LARGE": (
                "O manifesto Python do projeto excede o limite total local."
            ),
            "PROJECT_PYTHON_FILE_COUNT_EXCEEDED": (
                "O manifesto Python do projeto excede o limite local de arquivos."
            ),
            "PYTEST_VERIFIER_NOT_AVAILABLE": (
                "O pytest.exe controlado do venv não está disponível."
            ),
            "PYTEST_VERIFIER_LINK_NOT_ALLOWED": (
                "O pytest.exe controlado não pode ser link/junction."
            ),
            "PYTEST_VERIFIER_TOO_LARGE": (
                "O pytest.exe controlado excede o limite local."
            ),
            "PYTEST_VERIFIER_UNREADABLE": (
                "Não foi possível hashear o pytest.exe controlado."
            ),
            "PYTEST_PACKAGE_ROOT_UNAVAILABLE": (
                "Os roots pytest/_pytest do venv não estão disponíveis."
            ),
            "PYTEST_PACKAGE_LINK_NOT_ALLOWED": (
                "O estado pytest/_pytest contém link/junction e foi bloqueado."
            ),
            "PYTEST_PACKAGE_STATE_UNAVAILABLE": (
                "Não foi possível hashear o estado pytest/_pytest."
            ),
            "PYTEST_PACKAGE_FILE_TOO_LARGE": (
                "Um arquivo pytest/_pytest excede o limite local."
            ),
            "PYTEST_PACKAGE_TOTAL_TOO_LARGE": (
                "O estado pytest/_pytest excede o limite total local."
            ),
            "PYTEST_PACKAGE_FILE_COUNT_EXCEEDED": (
                "O estado pytest/_pytest excede o limite local de arquivos."
            ),
            "PYTHON_RUNTIME_NOT_AVAILABLE": (
                "O Scripts/python.exe do venv não está disponível."
            ),
            "PYTHON_RUNTIME_LINK_NOT_ALLOWED": (
                "O Scripts/python.exe do venv não pode ser link/junction."
            ),
            "PYTHON_RUNTIME_TOO_LARGE": (
                "O Scripts/python.exe do venv excede o limite local."
            ),
            "PYVENV_CONFIG_NOT_AVAILABLE": (
                "O pyvenv.cfg do venv não está disponível."
            ),
            "PYVENV_CONFIG_LINK_NOT_ALLOWED": (
                "O pyvenv.cfg do venv não pode ser link/junction."
            ),
            "PYVENV_CONFIG_TOO_LARGE": (
                "O pyvenv.cfg do venv excede o limite local."
            ),
            "PYTHON_RUNTIME_STATE_UNREADABLE": (
                "Não foi possível hashear o bootstrap Python do venv."
            ),
        }
        return ConfirmationPreview(
            allowed=False,
            text=messages.get(
                str(error),
                "Não foi possível preparar com segurança o lote de testes.",
            ),
        )

    def confirmation_preview(self, request: ActionRequest) -> ConfirmationPreview:
        raw_paths = request.arguments.get("paths")
        if not isinstance(raw_paths, list):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar a prévia: lote de caminhos inválido.",
            )

        try:
            evidence = self._adapter.preview_test_targets(raw_paths)
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível preparar com segurança o lote de testes.",
            )
        if evidence.get("error") is not None:
            return self._blocked_preview(evidence)

        try:
            verifier = self._adapter.preview_pytest_verifier()
            package_state = self._adapter.preview_pytest_package_state()
            runtime_state = self._adapter.preview_python_runtime_state()
        except (OSError, ValueError):
            return ConfirmationPreview(
                allowed=False,
                text="Não foi possível validar o runtime controlado do pytest.",
            )
        for state in (verifier, package_state, runtime_state):
            if state.get("error") is not None:
                return self._blocked_preview(state)

        targets = evidence["targets"]
        assert isinstance(targets, list)
        guard_targets = [
            {
                "path": str(target["path"]),
                "sha256": str(target["sha256"]),
            }
            for target in targets
        ]
        target_lines = "\n".join(
            (
                f"{index + 1}. {target['path']}\n"
                f"   SHA-256: {target['sha256']} | "
                f"{target['size_bytes']} byte(s)"
            )
            for index, target in enumerate(targets)
        )

        project_manifest_sha256 = str(
            evidence["project_python_manifest_sha256"]
        )
        pytest_verifier_path = str(verifier["pytest_verifier_path"])
        pytest_verifier_sha256 = str(verifier["pytest_verifier_sha256"])
        pytest_package_manifest_sha256 = str(
            package_state["pytest_package_manifest_sha256"]
        )
        python_runtime_state_sha256 = str(
            runtime_state["python_runtime_state_sha256"]
        )

        return ConfirmationPreview(
            allowed=True,
            text=(
                "EXECUTAR LOTE LIMITADO DE TESTES PYTHON\n"
                f"Arquivos aprovados: {len(targets)} "
                f"(limite {MIN_PYTHON_UNIT_TEST_MANY_FILES}–"
                f"{MAX_PYTHON_UNIT_TEST_MANY_FILES})\n"
                f"{target_lines}\n"
                f"Total selecionado: {evidence['selected_total_bytes']} byte(s); "
                f"limite de {MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES} byte(s).\n"
                "Manifesto Python do projeto: src/theos + tests/unit\n"
                f"Manifesto SHA-256 aprovado: {project_manifest_sha256}\n"
                f"pytest.exe aprovado: {pytest_verifier_path}\n"
                f"SHA-256 do pytest.exe: {pytest_verifier_sha256}\n"
                f"Manifesto pytest/_pytest SHA-256: "
                f"{pytest_package_manifest_sha256}\n"
                f"Estado bootstrap Python SHA-256: "
                f"{python_runtime_state_sha256}\n"
                f"Timeout por arquivo: {PYTHON_UNIT_TEST_TIMEOUT_SECONDS:g}s; "
                f"máximo de {MAX_PYTHON_UNIT_TEST_MANY_FILES} subprocessos pytest.\n"
                "RISCO PRIVILEGIADO: esta única aprovação autoriza executar "
                "sequencialmente somente os arquivos explícitos acima, cada um pelo "
                "runner single-file já controlado, com as permissões do usuário atual. "
                "THE OS NÃO fornece sandbox. Erro operacional/guard interrompe os "
                "arquivos restantes; falhas normais de teste são resultados de "
                "verificação e o lote pode continuar. Não há diretório, glob, node "
                "selector, flags fornecidas pelo modelo nem autoridade project-wide."
            ),
            execution_guard={
                _EXPECTED_TEST_BATCH_TARGETS: guard_targets,
                _EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256: (
                    project_manifest_sha256
                ),
                _EXPECTED_PYTEST_VERIFIER_PATH: pytest_verifier_path,
                _EXPECTED_PYTEST_VERIFIER_SHA256: pytest_verifier_sha256,
                _EXPECTED_PYTEST_PACKAGE_MANIFEST_SHA256: (
                    pytest_package_manifest_sha256
                ),
                _EXPECTED_PYTHON_RUNTIME_STATE_SHA256: (
                    python_runtime_state_sha256
                ),
            },
        )

    @staticmethod
    def _valid_expected_targets(value: object) -> bool:
        if not isinstance(value, list):
            return False
        if not (
            MIN_PYTHON_UNIT_TEST_MANY_FILES
            <= len(value)
            <= MAX_PYTHON_UNIT_TEST_MANY_FILES
        ):
            return False
        for item in value:
            if not isinstance(item, dict):
                return False
            if set(item) != {"path", "sha256"}:
                return False
            path = item.get("path")
            sha256 = item.get("sha256")
            if not isinstance(path, str) or not path:
                return False
            if not isinstance(sha256, str) or len(sha256) != 64:
                return False
        return True

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_paths = request.arguments.get("paths")
        expected_targets = request.arguments.get(_EXPECTED_TEST_BATCH_TARGETS)
        expected_project_manifest_sha256 = request.arguments.get(
            _EXPECTED_PROJECT_PYTHON_MANIFEST_SHA256
        )
        expected_pytest_verifier_path = request.arguments.get(
            _EXPECTED_PYTEST_VERIFIER_PATH
        )
        expected_pytest_verifier_sha256 = request.arguments.get(
            _EXPECTED_PYTEST_VERIFIER_SHA256
        )
        expected_pytest_package_manifest_sha256 = request.arguments.get(
            _EXPECTED_PYTEST_PACKAGE_MANIFEST_SHA256
        )
        expected_python_runtime_state_sha256 = request.arguments.get(
            _EXPECTED_PYTHON_RUNTIME_STATE_SHA256
        )

        if (
            not isinstance(raw_paths, list)
            or not self._valid_expected_targets(expected_targets)
            or not isinstance(expected_project_manifest_sha256, str)
            or len(expected_project_manifest_sha256) != 64
            or not isinstance(expected_pytest_verifier_path, str)
            or not expected_pytest_verifier_path
            or not isinstance(expected_pytest_verifier_sha256, str)
            or len(expected_pytest_verifier_sha256) != 64
            or not isinstance(expected_pytest_package_manifest_sha256, str)
            or len(expected_pytest_package_manifest_sha256) != 64
            or not isinstance(expected_python_runtime_state_sha256, str)
            or len(expected_python_runtime_state_sha256) != 64
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A execução do lote exige a prévia local aprovada.",
                error_code="PYTEST_BATCH_PREVIEW_REQUIRED",
            )

        try:
            preview = self._adapter.preview_test_targets(raw_paths)
        except (OSError, ValueError) as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui revalidar o lote de testes.",
                evidence={"exception": type(exc).__name__},
                error_code="PYTEST_BATCH_PREFLIGHT_FAILED",
            )
        if preview.get("error") is not None:
            error = str(preview["error"])
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O lote de testes foi bloqueado na revalidação.",
                evidence=preview,
                error_code=error,
            )

        current_targets = [
            {
                "path": str(target["path"]),
                "sha256": str(target["sha256"]),
            }
            for target in preview["targets"]
        ]
        if current_targets != expected_targets:
            evidence = dict(preview)
            evidence["error"] = "TEST_BATCH_CHANGED_AFTER_PREVIEW"
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A seleção ou o conteúdo do lote mudou após a aprovação; "
                    "pytest não foi iniciado."
                ),
                evidence=evidence,
                error_code="TEST_BATCH_CHANGED_AFTER_PREVIEW",
            )
        if (
            preview.get("project_python_manifest_sha256")
            != expected_project_manifest_sha256
        ):
            evidence = dict(preview)
            evidence["error"] = "PROJECT_PYTHON_STATE_CHANGED_AFTER_PREVIEW"
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "O estado Python do projeto mudou após a aprovação; "
                    "o lote não foi iniciado."
                ),
                evidence=evidence,
                error_code="PROJECT_PYTHON_STATE_CHANGED_AFTER_PREVIEW",
            )

        assert isinstance(expected_targets, list)
        aggregate: dict[str, object] = {
            "risk_boundary": "PRIVILEGED_BATCH_TEST_CODE_EXECUTION",
            "batch_composed_from_single_file_runner": True,
            "batch_files_approved": len(expected_targets),
            "batch_files_processed": 0,
            "pytest_processes_started": 0,
            "max_batch_files": MAX_PYTHON_UNIT_TEST_MANY_FILES,
            "max_batch_total_bytes": MAX_PYTHON_UNIT_TEST_MANY_TOTAL_BYTES,
            "max_pytest_processes": MAX_PYTHON_UNIT_TEST_MANY_FILES,
            "pytest_timeout_seconds_per_file": PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
            "shell_used": False,
            "sandboxed": False,
            "project_wide_test_authority": False,
            "raw_pytest_output_returned": False,
            "failure_diagnostics_untrusted": True,
            "failure_diagnostics": [],
            "failure_diagnostic_total": 0,
            "failure_diagnostics_truncated": False,
            "tests_run": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "files_failed": 0,
            "files_no_tests_collected": 0,
            "targets": list(expected_targets),
        }

        diagnostics: list[dict[str, object]] = []
        diagnostic_total = 0
        for index, target in enumerate(expected_targets):
            path = str(target["path"])
            sha256 = str(target["sha256"])
            try:
                result = self._adapter.run_test_file(
                    path,
                    expected_path=path,
                    expected_sha256=sha256,
                    expected_project_python_manifest_sha256=(
                        expected_project_manifest_sha256
                    ),
                    expected_pytest_verifier_path=expected_pytest_verifier_path,
                    expected_pytest_verifier_sha256=(
                        expected_pytest_verifier_sha256
                    ),
                    expected_pytest_package_manifest_sha256=(
                        expected_pytest_package_manifest_sha256
                    ),
                    expected_python_runtime_state_sha256=(
                        expected_python_runtime_state_sha256
                    ),
                )
            except (OSError, ValueError) as exc:
                aggregate.update(
                    {
                        "error": "PYTEST_BATCH_EXECUTION_FAILED",
                        "error_target_index": index,
                        "error_target_path": path,
                        "exception": type(exc).__name__,
                    }
                )
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        f"O lote foi interrompido no arquivo {index + 1} "
                        "por falha operacional."
                    ),
                    evidence=aggregate,
                    error_code="PYTEST_BATCH_EXECUTION_FAILED",
                )

            aggregate["batch_files_processed"] = index + 1
            if bool(result.get("test_code_executed")):
                aggregate["pytest_processes_started"] = int(
                    aggregate["pytest_processes_started"]
                ) + 1
            error = result.get("error")
            if isinstance(error, str):
                aggregate.update(
                    {
                        "error": error,
                        "error_target_index": index,
                        "error_target_path": path,
                    }
                )
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        f"O lote foi interrompido no arquivo {index + 1}: "
                        f"{error}."
                    ),
                    evidence=aggregate,
                    error_code=error,
                )

            aggregate["tests_run"] = int(aggregate["tests_run"]) + int(
                result.get("tests_run", 0)
            )
            aggregate["failures"] = int(aggregate["failures"]) + int(
                result.get("failures", 0)
            )
            aggregate["errors"] = int(aggregate["errors"]) + int(
                result.get("errors", 0)
            )
            aggregate["skipped"] = int(aggregate["skipped"]) + int(
                result.get("skipped", 0)
            )
            if not bool(result.get("passed")):
                aggregate["files_failed"] = int(aggregate["files_failed"]) + 1
            if bool(result.get("no_tests_collected")):
                aggregate["files_no_tests_collected"] = int(
                    aggregate["files_no_tests_collected"]
                ) + 1

            diagnostic_total += int(
                result.get("failure_diagnostic_total", 0)
            )
            raw_diagnostics = result.get("failure_diagnostics", [])
            if isinstance(raw_diagnostics, list):
                for diagnostic in raw_diagnostics:
                    if len(diagnostics) >= MAX_PYTEST_FAILURE_DIAGNOSTICS:
                        break
                    if not isinstance(diagnostic, dict):
                        continue
                    diagnostics.append(
                        {
                            "path": path,
                            **diagnostic,
                        }
                    )

        aggregate["failure_diagnostic_total"] = diagnostic_total
        aggregate["failure_diagnostics"] = diagnostics
        aggregate["failure_diagnostics_truncated"] = (
            diagnostic_total > len(diagnostics)
        )
        aggregate["all_passed"] = (
            int(aggregate["files_failed"]) == 0
            and int(aggregate["files_no_tests_collected"]) == 0
            and int(aggregate["tests_run"]) > 0
        )

        message = (
            "Lote controlado de testes concluído: "
            f"{aggregate['batch_files_processed']} arquivo(s) processado(s), "
            f"{aggregate['tests_run']} teste(s), "
            f"{aggregate['failures']} falha(s), "
            f"{aggregate['errors']} erro(s), "
            f"{aggregate['skipped']} ignorado(s)."
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=aggregate,
        )
