from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_PYTHON_UNIT_TEST_FILE_BYTES = 256 * 1024
MAX_PYTEST_JUNIT_BYTES = 256 * 1024
PYTHON_UNIT_TEST_TIMEOUT_SECONDS = 30.0
MAX_PYTEST_FAILURE_DIAGNOSTICS = 3
MAX_PYTEST_DIAGNOSTIC_NAME_CHARS = 160
MAX_PYTEST_DIAGNOSTIC_CLASSNAME_CHARS = 160
MAX_PYTEST_DIAGNOSTIC_MESSAGE_CHARS = 240
PROJECT_PYTHON_MANIFEST_ROOTS = ("src/theos", "tests/unit")
MAX_PROJECT_PYTHON_FILES = 256
MAX_PROJECT_PYTHON_FILE_BYTES = 256 * 1024
MAX_PROJECT_PYTHON_TOTAL_BYTES = 4 * 1024 * 1024
MAX_PYTEST_VERIFIER_BYTES = 4 * 1024 * 1024


class WindowsPythonUnitTestAdapter:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve(strict=True)
        self._tests_unit_root = (self._project_root / "tests" / "unit").resolve(
            strict=True
        )

    @property
    def project_root(self) -> Path:
        return self._project_root

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        if path.is_symlink():
            return True
        isjunction = getattr(os.path, "isjunction", None)
        return bool(isjunction(path)) if callable(isjunction) else False

    def _resolve_explicit_unit_test(
        self,
        raw_path: str,
    ) -> tuple[Path | None, str | None]:
        normalized = raw_path.strip()
        if not normalized:
            return None, "PATH_REQUIRED"

        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = self._project_root / candidate
        lexical = Path(os.path.abspath(candidate))

        try:
            lexical.relative_to(self._tests_unit_root)
        except ValueError:
            return None, "TEST_TARGET_OUTSIDE_UNIT_ROOT"

        current = lexical
        while True:
            if current.exists() and self._is_link_like(current):
                return None, "LINK_TARGET_NOT_ALLOWED"
            if current == self._tests_unit_root:
                break
            if self._tests_unit_root not in current.parents:
                return None, "TEST_TARGET_OUTSIDE_UNIT_ROOT"
            current = current.parent

        try:
            resolved = lexical.resolve(strict=True)
        except FileNotFoundError:
            return lexical, "PATH_NOT_FOUND"

        try:
            resolved.relative_to(self._tests_unit_root)
        except ValueError:
            return None, "TEST_TARGET_OUTSIDE_UNIT_ROOT"

        if not resolved.is_file():
            return resolved, "PATH_NOT_FILE"
        if resolved.suffix.casefold() != ".py" or not resolved.name.startswith("test_"):
            return resolved, "UNIT_TEST_FILE_REQUIRED"

        return resolved, None

    def _project_python_manifest(self) -> dict[str, object]:
        records: list[tuple[str, int, str]] = []
        total_bytes = 0
        try:
            for root_label in PROJECT_PYTHON_MANIFEST_ROOTS:
                root = self._project_root / Path(root_label)
                if not root.exists() or not root.is_dir():
                    return {"error": "PROJECT_PYTHON_ROOT_UNAVAILABLE"}
                if self._is_link_like(root):
                    return {"error": "PROJECT_PYTHON_LINK_NOT_ALLOWED"}

                for current_raw, dirnames, filenames in os.walk(
                    root,
                    topdown=True,
                    followlinks=False,
                ):
                    current = Path(current_raw)
                    if self._is_link_like(current):
                        return {"error": "PROJECT_PYTHON_LINK_NOT_ALLOWED"}

                    for dirname in tuple(dirnames):
                        child = current / dirname
                        if self._is_link_like(child):
                            return {"error": "PROJECT_PYTHON_LINK_NOT_ALLOWED"}
                    dirnames[:] = sorted(dirnames, key=str.casefold)

                    for filename in sorted(filenames, key=str.casefold):
                        if not filename.casefold().endswith(".py"):
                            continue
                        target = current / filename
                        if self._is_link_like(target):
                            return {"error": "PROJECT_PYTHON_LINK_NOT_ALLOWED"}
                        if not target.is_file():
                            return {"error": "PROJECT_PYTHON_STATE_UNAVAILABLE"}

                        payload = target.read_bytes()
                        size_bytes = len(payload)
                        if size_bytes > MAX_PROJECT_PYTHON_FILE_BYTES:
                            return {"error": "PROJECT_PYTHON_FILE_TOO_LARGE"}

                        total_bytes += size_bytes
                        if total_bytes > MAX_PROJECT_PYTHON_TOTAL_BYTES:
                            return {"error": "PROJECT_PYTHON_TOTAL_TOO_LARGE"}

                        relative = target.relative_to(self._project_root).as_posix()
                        records.append(
                            (
                                relative,
                                size_bytes,
                                hashlib.sha256(payload).hexdigest(),
                            )
                        )
                        if len(records) > MAX_PROJECT_PYTHON_FILES:
                            return {"error": "PROJECT_PYTHON_FILE_COUNT_EXCEEDED"}
        except OSError:
            return {"error": "PROJECT_PYTHON_STATE_UNAVAILABLE"}

        records.sort(key=lambda item: item[0].casefold())
        digest = hashlib.sha256()
        for relative, size_bytes, sha256 in records:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(size_bytes).encode("ascii"))
            digest.update(b"\0")
            digest.update(sha256.encode("ascii"))
            digest.update(b"\n")

        return {
            "project_python_manifest_sha256": digest.hexdigest(),
            "project_python_file_count": len(records),
            "project_python_total_bytes": total_bytes,
            "project_python_manifest_roots": list(PROJECT_PYTHON_MANIFEST_ROOTS),
            "project_python_manifest_entries_returned": False,
            "project_python_source_content_returned": False,
            "max_project_python_files": MAX_PROJECT_PYTHON_FILES,
            "max_project_python_file_bytes": MAX_PROJECT_PYTHON_FILE_BYTES,
            "max_project_python_total_bytes": MAX_PROJECT_PYTHON_TOTAL_BYTES,
        }

    def preview_test_target(self, raw_path: str) -> dict[str, object]:
        path, error = self._resolve_explicit_unit_test(raw_path)
        evidence: dict[str, object] = {
            "project_root": str(self._project_root),
            "tests_unit_root": str(self._tests_unit_root),
            "max_file_bytes": MAX_PYTHON_UNIT_TEST_FILE_BYTES,
            "pytest_timeout_seconds": PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
            "source_content_returned": False,
            "test_code_executed": False,
            "sandboxed": False,
            "external_side_effects_not_contained": True,
        }
        if path is not None:
            evidence["path"] = str(path)
        if error is not None:
            evidence["error"] = error
            return evidence

        assert path is not None
        size_bytes = path.stat().st_size
        evidence["size_bytes"] = size_bytes
        if size_bytes > MAX_PYTHON_UNIT_TEST_FILE_BYTES:
            evidence["error"] = "FILE_TOO_LARGE"
            return evidence

        payload = path.read_bytes()
        evidence.update(
            {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes_hashed": len(payload),
                "hash_only_preflight": True,
            }
        )

        manifest = self._project_python_manifest()
        manifest_error = manifest.get("error")
        if isinstance(manifest_error, str):
            evidence["error"] = manifest_error
            return evidence
        evidence.update(manifest)
        return evidence

    @staticmethod
    def _pytest_executable() -> Path:
        return Path(sys.executable).resolve().with_name("pytest.exe")

    def preview_pytest_verifier(self) -> dict[str, object]:
        raw_path = self._pytest_executable()
        path = Path(os.path.abspath(raw_path))
        evidence: dict[str, object] = {
            "pytest_verifier_path": str(path),
            "max_pytest_verifier_bytes": MAX_PYTEST_VERIFIER_BYTES,
            "pytest_verifier_content_returned": False,
        }

        try:
            if not path.exists() or not path.is_file():
                evidence["error"] = "PYTEST_VERIFIER_NOT_AVAILABLE"
                return evidence
            if self._is_link_like(path):
                evidence["error"] = "PYTEST_VERIFIER_LINK_NOT_ALLOWED"
                return evidence
            resolved = path.resolve(strict=True)
            if self._is_link_like(resolved):
                evidence["error"] = "PYTEST_VERIFIER_LINK_NOT_ALLOWED"
                return evidence
            size_bytes = resolved.stat().st_size
            evidence["pytest_verifier_path"] = str(resolved)
            evidence["pytest_verifier_size_bytes"] = size_bytes
            if size_bytes > MAX_PYTEST_VERIFIER_BYTES:
                evidence["error"] = "PYTEST_VERIFIER_TOO_LARGE"
                return evidence
            payload = resolved.read_bytes()
        except OSError:
            evidence["error"] = "PYTEST_VERIFIER_UNREADABLE"
            return evidence

        evidence.update(
            {
                "pytest_verifier_sha256": hashlib.sha256(payload).hexdigest(),
                "pytest_verifier_hash_only_preflight": True,
            }
        )
        return evidence

    @staticmethod
    def _bounded_junit_attribute(
        value: str | None,
        *,
        limit: int,
    ) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if len(normalized) > limit:
            return normalized[: limit - 1] + "…"
        return normalized

    @classmethod
    def _parse_junit_report(cls, report: Path) -> dict[str, object]:
        root = ET.parse(report).getroot()
        suites = []
        if root.tag.rsplit("}", 1)[-1] == "testsuite":
            suites = [root]
        else:
            suites = [
                element
                for element in root
                if element.tag.rsplit("}", 1)[-1] == "testsuite"
            ]
        if not suites:
            raise ValueError("missing testsuite")

        totals = {
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
        for suite in suites:
            for key in totals:
                raw_value = suite.attrib.get(key, "0")
                value = int(raw_value)
                if value < 0:
                    raise ValueError("negative junit count")
                totals[key] += value

        diagnostics: list[dict[str, object]] = []
        diagnostic_total = 0
        for suite in suites:
            for testcase in suite.iter():
                if testcase.tag.rsplit("}", 1)[-1] != "testcase":
                    continue
                for outcome in testcase:
                    kind = outcome.tag.rsplit("}", 1)[-1]
                    if kind not in {"failure", "error"}:
                        continue
                    diagnostic_total += 1
                    if len(diagnostics) >= MAX_PYTEST_FAILURE_DIAGNOSTICS:
                        continue
                    diagnostics.append(
                        {
                            "kind": kind,
                            "test_name": cls._bounded_junit_attribute(
                                testcase.attrib.get("name"),
                                limit=MAX_PYTEST_DIAGNOSTIC_NAME_CHARS,
                            ),
                            "class_name": cls._bounded_junit_attribute(
                                testcase.attrib.get("classname"),
                                limit=MAX_PYTEST_DIAGNOSTIC_CLASSNAME_CHARS,
                            ),
                            "message": cls._bounded_junit_attribute(
                                outcome.attrib.get("message"),
                                limit=MAX_PYTEST_DIAGNOSTIC_MESSAGE_CHARS,
                            ),
                        }
                    )

        return {
            **totals,
            "failure_diagnostic_total": diagnostic_total,
            "failure_diagnostics": diagnostics,
            "failure_diagnostics_truncated": (
                diagnostic_total > MAX_PYTEST_FAILURE_DIAGNOSTICS
            ),
        }

    def run_test_file(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_sha256: str,
        expected_project_python_manifest_sha256: str,
        expected_pytest_verifier_path: str,
        expected_pytest_verifier_sha256: str,
    ) -> dict[str, object]:
        preview = self.preview_test_target(raw_path)
        evidence = dict(preview)
        evidence.update(
            {
                "risk_boundary": "PRIVILEGED_TEST_CODE_EXECUTION",
                "pytest_executable_fixed": True,
                "pytest_verifier_identity_guard_enabled": True,
                "pytest_arguments_fixed": True,
                "shell_used": False,
                "plugin_autoload_enabled": False,
                "implicit_pytest_config_enabled": False,
                "ambient_pytest_environment_scrubbed": True,
                "ambient_python_environment_scrubbed": True,
                "python_user_site_enabled": False,
                "python_safe_path_enabled": True,
                "python_import_environment_is_hermetic": False,
                "venv_site_packages_may_execute_startup_hooks": True,
                "controlled_pytest_config_enabled": True,
                "controlled_pytest_rootdir_enabled": True,
                "conftest_loading_enabled": False,
                "pytest_cache_enabled": False,
                "bytecode_write_enabled": False,
                "raw_pytest_output_returned": False,
                "junit_bounded_structured_evidence_only": True,
                "junit_failure_body_returned": False,
                "failure_diagnostics_untrusted": True,
                "max_failure_diagnostics": MAX_PYTEST_FAILURE_DIAGNOSTICS,
                "test_code_executed": False,
                "project_imports_may_execute": True,
                "project_python_manifest_guard_enabled": True,
                "project_python_manifest_is_dependency_closure": False,
                "sandboxed": False,
                "external_side_effects_not_contained": True,
            }
        )
        if evidence.get("error") is not None:
            return evidence

        path = Path(str(evidence["path"]))
        if str(path) != expected_path or evidence.get("sha256") != expected_sha256:
            evidence["error"] = "TEST_TARGET_CHANGED_AFTER_PREVIEW"
            return evidence
        if (
            evidence.get("project_python_manifest_sha256")
            != expected_project_python_manifest_sha256
        ):
            evidence["error"] = "PROJECT_PYTHON_STATE_CHANGED_AFTER_PREVIEW"
            return evidence

        verifier = self.preview_pytest_verifier()
        verifier_error = verifier.get("error")
        if isinstance(verifier_error, str):
            evidence.update(verifier)
            return evidence
        evidence.update(verifier)
        if (
            evidence.get("pytest_verifier_path") != expected_pytest_verifier_path
            or evidence.get("pytest_verifier_sha256")
            != expected_pytest_verifier_sha256
        ):
            evidence["error"] = "PYTEST_VERIFIER_CHANGED_AFTER_PREVIEW"
            return evidence

        pytest_executable = Path(expected_pytest_verifier_path)

        environment = os.environ.copy()
        for key in tuple(environment):
            if key.startswith(("PYTEST_", "PYTHON")):
                environment.pop(key, None)
        environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONSAFEPATH"] = "1"
        environment["NO_COLOR"] = "1"

        with tempfile.TemporaryDirectory(prefix="theos-pytest-") as temp_dir:
            report = Path(temp_dir) / "junit.xml"
            config = Path(temp_dir) / "pytest.ini"
            config.write_text("[pytest]\n", encoding="utf-8", newline="\n")
            command = [
                str(pytest_executable),
                "--disable-plugin-autoload",
                "-c",
                str(config),
                "--rootdir",
                str(self._project_root),
                "-q",
                "--disable-warnings",
                "--maxfail=1",
                "--tb=no",
                "--noconftest",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report}",
                str(path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=self._project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    shell=False,
                    timeout=PYTHON_UNIT_TEST_TIMEOUT_SECONDS,
                    env=environment,
                )
            except subprocess.TimeoutExpired:
                evidence["test_code_executed"] = True
                after_verifier = self.preview_pytest_verifier()
                after_verifier_error = after_verifier.get("error")
                if (
                    isinstance(after_verifier_error, str)
                    or after_verifier.get("pytest_verifier_path")
                    != expected_pytest_verifier_path
                    or after_verifier.get("pytest_verifier_sha256")
                    != expected_pytest_verifier_sha256
                ):
                    evidence.update(
                        {
                            "pytest_verifier_unchanged": False,
                            "error": "PYTEST_VERIFIER_CHANGED_DURING_RUN",
                        }
                    )
                    return evidence
                evidence.update(
                    {
                        "pytest_verifier_unchanged": True,
                        "error": "PYTEST_TIMEOUT",
                    }
                )
                return evidence

            evidence.update(
                {
                    "test_code_executed": True,
                    "pytest_exit_code": completed.returncode,
                }
            )

            after_verifier = self.preview_pytest_verifier()
            after_verifier_error = after_verifier.get("error")
            if (
                isinstance(after_verifier_error, str)
                or after_verifier.get("pytest_verifier_path")
                != expected_pytest_verifier_path
                or after_verifier.get("pytest_verifier_sha256")
                != expected_pytest_verifier_sha256
            ):
                evidence.update(
                    {
                        "pytest_verifier_unchanged": False,
                        "error": "PYTEST_VERIFIER_CHANGED_DURING_RUN",
                    }
                )
                return evidence
            evidence["pytest_verifier_unchanged"] = True

            try:
                after_payload = path.read_bytes()
            except OSError:
                evidence.update(
                    {
                        "target_unchanged": False,
                        "error": "TEST_TARGET_CHANGED_DURING_RUN",
                    }
                )
                return evidence

            after_sha256 = hashlib.sha256(after_payload).hexdigest()
            evidence["after_sha256"] = after_sha256
            evidence["target_unchanged"] = after_sha256 == expected_sha256
            if after_sha256 != expected_sha256:
                evidence["error"] = "TEST_TARGET_CHANGED_DURING_RUN"
                return evidence

            after_manifest = self._project_python_manifest()
            after_manifest_error = after_manifest.get("error")
            if isinstance(after_manifest_error, str):
                evidence.update(
                    {
                        "project_python_state_unchanged": False,
                        "project_python_state_after_error": after_manifest_error,
                        "error": "PROJECT_PYTHON_STATE_INVALID_AFTER_RUN",
                    }
                )
                return evidence

            after_manifest_sha256 = str(
                after_manifest["project_python_manifest_sha256"]
            )
            evidence["after_project_python_manifest_sha256"] = (
                after_manifest_sha256
            )
            evidence["project_python_state_unchanged"] = (
                after_manifest_sha256
                == expected_project_python_manifest_sha256
            )
            if not evidence["project_python_state_unchanged"]:
                evidence["error"] = "PROJECT_PYTHON_STATE_CHANGED_DURING_RUN"
                return evidence

            if completed.returncode not in {0, 1, 5}:
                evidence["error"] = "PYTEST_PROCESS_FAILED"
                return evidence

            if not report.is_file():
                evidence["error"] = "PYTEST_REPORT_MISSING"
                return evidence
            report_size = report.stat().st_size
            evidence["junit_report_bytes"] = report_size
            if report_size > MAX_PYTEST_JUNIT_BYTES:
                evidence["error"] = "PYTEST_REPORT_TOO_LARGE"
                return evidence

            try:
                summary = self._parse_junit_report(report)
            except (ET.ParseError, OSError, ValueError):
                evidence["error"] = "PYTEST_REPORT_INVALID"
                return evidence

        tests_run = summary["tests"]
        failures = summary["failures"]
        errors = summary["errors"]
        skipped = summary["skipped"]
        evidence.update(
            {
                "tests_run": tests_run,
                "failures": failures,
                "errors": errors,
                "skipped": skipped,
                "failure_diagnostic_total": summary["failure_diagnostic_total"],
                "failure_diagnostics": summary["failure_diagnostics"],
                "failure_diagnostics_truncated": summary[
                    "failure_diagnostics_truncated"
                ],
                "passed": (
                    completed.returncode == 0
                    and tests_run > 0
                    and failures == 0
                    and errors == 0
                ),
                "no_tests_collected": completed.returncode == 5 or tests_run == 0,
            }
        )
        return evidence
