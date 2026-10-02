from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

MAX_GIT_EXECUTABLE_BYTES = 16 * 1024 * 1024
MAX_GIT_STATUS_OUTPUT_BYTES = 128 * 1024
MAX_GIT_STATUS_ENTRIES = 64
MAX_GIT_STATUS_PATH_CHARS = 512
GIT_STATUS_TIMEOUT_SECONDS = 5.0


class WindowsLocalGitAdapter:
    """Bounded read-only Git inspection for THE OS's own checkout."""

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        if path.is_symlink():
            return True
        try:
            attributes = path.lstat().st_file_attributes
        except (AttributeError, OSError):
            return False
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)

    @staticmethod
    def _git_executable() -> Path | None:
        raw = shutil.which("git.exe") or shutil.which("git")
        if raw is None:
            return None
        return Path(raw)

    def preview_git_executable(self) -> dict[str, object]:
        raw_path = self._git_executable()
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "max_git_executable_bytes": MAX_GIT_EXECUTABLE_BYTES,
            "git_executable_content_returned": False,
        }
        if raw_path is None:
            evidence["error"] = "GIT_EXECUTABLE_NOT_AVAILABLE"
            return evidence

        path = Path(os.path.abspath(raw_path))
        evidence["git_executable_path"] = str(path)
        try:
            if not path.exists() or not path.is_file():
                evidence["error"] = "GIT_EXECUTABLE_NOT_AVAILABLE"
                return evidence
            if self._is_link_like(path):
                evidence["error"] = "GIT_EXECUTABLE_LINK_NOT_ALLOWED"
                return evidence
            resolved = path.resolve(strict=True)
            if self._is_link_like(resolved):
                evidence["error"] = "GIT_EXECUTABLE_LINK_NOT_ALLOWED"
                return evidence
            size_bytes = resolved.stat().st_size
            evidence["git_executable_path"] = str(resolved)
            evidence["git_executable_size_bytes"] = size_bytes
            if size_bytes > MAX_GIT_EXECUTABLE_BYTES:
                evidence["error"] = "GIT_EXECUTABLE_TOO_LARGE"
                return evidence
            payload = resolved.read_bytes()
        except OSError:
            evidence["error"] = "GIT_EXECUTABLE_UNREADABLE"
            return evidence

        evidence["git_executable_sha256"] = hashlib.sha256(payload).hexdigest()
        return evidence

    @staticmethod
    def _controlled_environment() -> dict[str, str]:
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.upper().startswith("GIT_"):
                environment.pop(key, None)
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["NO_COLOR"] = "1"
        return environment

    def _run_git(
        self,
        git_executable: Path,
        arguments: list[str],
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                str(git_executable),
                "-C",
                str(self._repository_root),
                *arguments,
            ],
            cwd=self._repository_root,
            shell=False,
            check=False,
            capture_output=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
            env=self._controlled_environment(),
        )

    @staticmethod
    def _decode_small_output(
        payload: bytes,
        *,
        error_code: str,
    ) -> str:
        if len(payload) > MAX_GIT_STATUS_OUTPUT_BYTES:
            raise RuntimeError(error_code)
        try:
            return payload.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise RuntimeError("GIT_STATUS_OUTPUT_ENCODING_FAILED") from exc

    @staticmethod
    def _bounded_path(value: str) -> tuple[str, bool]:
        if len(value) <= MAX_GIT_STATUS_PATH_CHARS:
            return value, False
        return value[: MAX_GIT_STATUS_PATH_CHARS - 3] + "...", True

    def _parse_status(
        self,
        payload: bytes,
    ) -> dict[str, object]:
        if len(payload) > MAX_GIT_STATUS_OUTPUT_BYTES:
            return {"error": "GIT_STATUS_OUTPUT_TOO_LARGE"}

        records = payload.split(b"\0")
        entries: list[dict[str, object]] = []
        observed = 0
        path_truncated = False
        index = 0

        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4 or record[2:3] != b" ":
                return {"error": "GIT_STATUS_OUTPUT_INVALID"}

            try:
                status_code = record[:2].decode("ascii")
                path_text = record[3:].decode("utf-8")
            except UnicodeDecodeError:
                return {"error": "GIT_STATUS_OUTPUT_ENCODING_FAILED"}

            bounded_path, truncated = self._bounded_path(path_text)
            path_truncated = path_truncated or truncated
            item: dict[str, object] = {
                "index_status": status_code[0],
                "worktree_status": status_code[1],
                "path": bounded_path,
            }

            if "R" in status_code or "C" in status_code:
                if index >= len(records) or not records[index]:
                    return {"error": "GIT_STATUS_OUTPUT_INVALID"}
                try:
                    original_text = records[index].decode("utf-8")
                except UnicodeDecodeError:
                    return {"error": "GIT_STATUS_OUTPUT_ENCODING_FAILED"}
                index += 1
                bounded_original, original_truncated = self._bounded_path(
                    original_text
                )
                path_truncated = path_truncated or original_truncated
                item["original_path"] = bounded_original

            observed += 1
            if len(entries) < MAX_GIT_STATUS_ENTRIES:
                entries.append(item)

        return {
            "entries": entries,
            "observed_changes": observed,
            "returned_changes": len(entries),
            "entries_truncated": observed > len(entries),
            "path_text_truncated": path_truncated,
        }

    def snapshot(
        self,
        *,
        expected_git_executable_path: str,
        expected_git_executable_sha256: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "git_command_authority": "FIXED_STATUS_ONLY",
            "git_arguments_model_controlled": False,
            "repository_path_model_controlled": False,
            "shell_used": False,
            "git_optional_locks_disabled": True,
            "git_environment_inherited_git_keys_scrubbed": True,
            "raw_stdout_returned": False,
            "raw_stderr_returned": False,
            "max_status_output_bytes": MAX_GIT_STATUS_OUTPUT_BYTES,
            "max_status_entries": MAX_GIT_STATUS_ENTRIES,
            "max_status_path_chars": MAX_GIT_STATUS_PATH_CHARS,
        }

        verifier = self.preview_git_executable()
        verifier_error = verifier.get("error")
        if isinstance(verifier_error, str):
            evidence.update(verifier)
            return evidence
        evidence.update(verifier)

        if (
            verifier.get("git_executable_path") != expected_git_executable_path
            or verifier.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"
            return evidence

        git_executable = Path(expected_git_executable_path)

        try:
            root_result = self._run_git(
                git_executable,
                ["rev-parse", "--show-toplevel"],
            )
            if root_result.returncode != 0:
                evidence["error"] = "GIT_REPOSITORY_NOT_AVAILABLE"
                return evidence
            root_text = self._decode_small_output(
                root_result.stdout,
                error_code="GIT_STATUS_OUTPUT_TOO_LARGE",
            )
            actual_root = Path(root_text).resolve(strict=False)
            if os.path.normcase(str(actual_root)) != os.path.normcase(
                str(self._repository_root)
            ):
                evidence["error"] = "GIT_REPOSITORY_ROOT_MISMATCH"
                return evidence

            head_result = self._run_git(
                git_executable,
                ["rev-parse", "--verify", "HEAD"],
            )
            if head_result.returncode != 0:
                evidence["error"] = "GIT_HEAD_NOT_AVAILABLE"
                return evidence
            head_sha = self._decode_small_output(
                head_result.stdout,
                error_code="GIT_STATUS_OUTPUT_TOO_LARGE",
            )
            if re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha) is None:
                evidence["error"] = "GIT_HEAD_OUTPUT_INVALID"
                return evidence

            branch_result = self._run_git(
                git_executable,
                ["symbolic-ref", "--quiet", "--short", "HEAD"],
            )
            if branch_result.returncode == 0:
                branch = self._decode_small_output(
                    branch_result.stdout,
                    error_code="GIT_STATUS_OUTPUT_TOO_LARGE",
                )
                if not branch:
                    evidence["error"] = "GIT_BRANCH_OUTPUT_INVALID"
                    return evidence
                detached = False
            elif branch_result.returncode == 1:
                branch = None
                detached = True
            else:
                evidence["error"] = "GIT_BRANCH_READ_FAILED"
                return evidence

            status_result = self._run_git(
                git_executable,
                [
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=normal",
                ],
            )
            if status_result.returncode != 0:
                evidence["error"] = "GIT_STATUS_FAILED"
                return evidence
            parsed = self._parse_status(status_result.stdout)
            if parsed.get("error") is not None:
                evidence.update(parsed)
                return evidence
        except subprocess.TimeoutExpired:
            evidence["error"] = "GIT_STATUS_TIMEOUT"
            return evidence
        except (OSError, RuntimeError) as exc:
            reason = str(exc)
            if reason in {
                "GIT_STATUS_OUTPUT_TOO_LARGE",
                "GIT_STATUS_OUTPUT_ENCODING_FAILED",
            }:
                evidence["error"] = reason
            else:
                evidence["error"] = "GIT_STATUS_FAILED"
            return evidence

        after_verifier = self.preview_git_executable()
        after_error = after_verifier.get("error")
        if (
            isinstance(after_error, str)
            or after_verifier.get("git_executable_path")
            != expected_git_executable_path
            or after_verifier.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["git_executable_unchanged"] = False
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_DURING_STATUS"
            return evidence

        evidence.update(parsed)
        evidence.update(
            {
                "head_sha": head_sha.lower(),
                "branch": branch,
                "detached_head": detached,
                "clean": int(parsed["observed_changes"]) == 0,
                "git_executable_unchanged": True,
            }
        )
        return evidence
