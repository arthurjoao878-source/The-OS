from __future__ import annotations

from pathlib import Path

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.integrations.windows.python_tests import (
    MAX_PYTHON_UNIT_TEST_FILE_BYTES,
    PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
    WindowsPythonUnitTestAdapter,
)

_EXPECTED_TEST_PATH = "_expected_test_path"
_EXPECTED_TEST_SHA256 = "_expected_test_sha256"


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
        return ConfirmationPreview(
            allowed=True,
            text=(
                "EXECUTAR UM ARQUIVO DE TESTE PYTHON\n"
                f"Caminho aprovado: {path}\n"
                f"SHA-256 aprovado: {sha256}\n"
                f"Limite do arquivo: {MAX_PYTHON_UNIT_TEST_FILE_BYTES} byte(s).\n"
                f"Timeout: {PYTHON_UNIT_TEST_TIMEOUT_SECONDS:g}s.\n"
                "RISCO PRIVILEGIADO: pytest executará código Python do arquivo de teste "
                "e dos módulos que ele importar com as permissões do usuário atual. "
                "THE OS NÃO fornece sandbox para esses efeitos externos.\n"
                "A seleção é estreita: somente este tests/unit/test_*.py explícito. "
                "THE OS usa somente pytest.exe do mesmo venv, argv fixo, sem shell, "
                "sem plugin autoload, sem conftest, sem cacheprovider e sem bytecode. "
                "stdout/stderr brutos não são enviados ao modelo; somente contagens "
                "estruturadas do relatório JUnit temporário."
            ),
            execution_guard={
                _EXPECTED_TEST_PATH: path,
                _EXPECTED_TEST_SHA256: sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_path = str(request.arguments.get("path", "")).strip()
        expected_path = request.arguments.get(_EXPECTED_TEST_PATH)
        expected_sha256 = request.arguments.get(_EXPECTED_TEST_SHA256)
        if (
            not raw_path
            or not isinstance(expected_path, str)
            or not expected_path
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
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
                "PYTEST_VERIFIER_NOT_AVAILABLE": (
                    "O pytest.exe controlado do venv não está disponível."
                ),
                "PYTEST_TIMEOUT": "O teste excedeu o timeout local de 30 segundos.",
                "TEST_TARGET_CHANGED_DURING_RUN": (
                    "O arquivo de teste mudou durante a execução; resultado descartado."
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
            message = (
                f"Teste unitário controlado concluiu com falha em {path.name}: "
                f"{failures} falha(s), {errors} erro(s), "
                f"{tests_run} teste(s) executado(s)."
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )
