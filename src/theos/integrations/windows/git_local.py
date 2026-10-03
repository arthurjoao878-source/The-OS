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

MAX_GIT_DIFF_FILE_BYTES = 256 * 1024
MAX_GIT_DIFF_OUTPUT_BYTES = 32 * 1024
MAX_GIT_DIFF_LINES = 400
GIT_DIFF_TIMEOUT_SECONDS = 5.0

MAX_GIT_STAGE_FILE_BYTES = 256 * 1024
GIT_STAGE_TIMEOUT_SECONDS = 5.0

MAX_GIT_UNSTAGE_FILE_BYTES = 256 * 1024
GIT_UNSTAGE_TIMEOUT_SECONDS = 5.0

MAX_GIT_STAGE_NEW_FILE_BYTES = 256 * 1024


class WindowsLocalGitAdapter:
    """Bounded local Git operations for THE OS's own checkout."""

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
        environment["GIT_PAGER"] = "cat"
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
    def _controlled_mutation_environment() -> dict[str, str]:
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.upper().startswith("GIT_"):
                environment.pop(key, None)
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["GIT_PAGER"] = "cat"
        environment["NO_COLOR"] = "1"
        return environment

    def _run_git_mutating(
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
            timeout=GIT_STAGE_TIMEOUT_SECONDS,
            env=self._controlled_mutation_environment(),
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


    @staticmethod
    def _normalize_repo_relative_path(raw_path: str) -> str | None:
        value = raw_path.strip().replace("\\", "/")
        if (
            not value
            or len(value) > MAX_GIT_STATUS_PATH_CHARS
            or any(character in value for character in ("\0", "\r", "\n"))
            or value.startswith("/")
            or ":" in value
        ):
            return None
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return None
        return "/".join(parts)

    def _resolve_diff_target(
        self,
        raw_path: str,
    ) -> tuple[Path | None, str | None, str | None]:
        relative = self._normalize_repo_relative_path(raw_path)
        if relative is None:
            return None, None, "GIT_DIFF_PATH_INVALID"

        candidate = self._repository_root.joinpath(*relative.split("/"))
        try:
            if not candidate.exists():
                return None, relative, "GIT_DIFF_FILE_NOT_FOUND"
            if not candidate.is_file():
                return None, relative, "GIT_DIFF_FILE_REQUIRED"
            if self._is_link_like(candidate):
                return None, relative, "GIT_DIFF_LINK_NOT_ALLOWED"
            resolved = candidate.resolve(strict=True)
            if self._is_link_like(resolved):
                return None, relative, "GIT_DIFF_LINK_NOT_ALLOWED"
            try:
                resolved_relative = resolved.relative_to(self._repository_root)
            except ValueError:
                return None, relative, "GIT_DIFF_PATH_OUTSIDE_REPOSITORY"
        except OSError:
            return None, relative, "GIT_DIFF_TARGET_UNAVAILABLE"

        normalized_relative = resolved_relative.as_posix()
        return resolved, normalized_relative, None

    def preview_diff_target(self, raw_path: str) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "requested_path": raw_path.strip(),
            "max_diff_file_bytes": MAX_GIT_DIFF_FILE_BYTES,
            "max_diff_output_bytes": MAX_GIT_DIFF_OUTPUT_BYTES,
            "max_diff_lines": MAX_GIT_DIFF_LINES,
            "diff_content_returned": False,
            "tracked_existing_file_required": True,
        }

        path, relative_path, error = self._resolve_diff_target(raw_path)
        if error is not None:
            evidence["error"] = error
            if relative_path is not None:
                evidence["path"] = relative_path
            return evidence
        assert path is not None
        assert relative_path is not None
        evidence["path"] = relative_path

        try:
            size_bytes = path.stat().st_size
            evidence["file_size_bytes"] = size_bytes
            if size_bytes > MAX_GIT_DIFF_FILE_BYTES:
                evidence["error"] = "GIT_DIFF_FILE_TOO_LARGE"
                return evidence
            payload = path.read_bytes()
        except OSError:
            evidence["error"] = "GIT_DIFF_TARGET_UNAVAILABLE"
            return evidence

        if b"\0" in payload[:8192]:
            evidence["error"] = "GIT_DIFF_BINARY_NOT_ALLOWED"
            return evidence

        target_sha256 = hashlib.sha256(payload).hexdigest()
        evidence["target_sha256"] = target_sha256

        verifier = self.preview_git_executable()
        verifier_error = verifier.get("error")
        if isinstance(verifier_error, str):
            evidence.update(verifier)
            return evidence
        evidence.update(verifier)
        git_executable = Path(str(verifier["git_executable_path"]))

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
            evidence["head_sha"] = head_sha.lower()

            tracked_result = self._run_git(
                git_executable,
                [
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    relative_path,
                ],
            )
            if tracked_result.returncode != 0:
                evidence["error"] = "GIT_DIFF_TRACKED_FILE_REQUIRED"
                return evidence

            changed_result = self._run_git(
                git_executable,
                [
                    "diff",
                    "--quiet",
                    "--no-ext-diff",
                    "--no-textconv",
                    "HEAD",
                    "--",
                    relative_path,
                ],
            )
            if changed_result.returncode == 0:
                evidence["error"] = "GIT_DIFF_NO_CHANGES"
                return evidence
            if changed_result.returncode != 1:
                evidence["error"] = "GIT_DIFF_PREFLIGHT_FAILED"
                return evidence
        except subprocess.TimeoutExpired:
            evidence["error"] = "GIT_DIFF_TIMEOUT"
            return evidence
        except (OSError, RuntimeError):
            evidence["error"] = "GIT_DIFF_PREFLIGHT_FAILED"
            return evidence

        try:
            after_payload = path.read_bytes()
        except OSError:
            evidence["error"] = "GIT_DIFF_TARGET_CHANGED_DURING_PREVIEW"
            return evidence
        if hashlib.sha256(after_payload).hexdigest() != target_sha256:
            evidence["error"] = "GIT_DIFF_TARGET_CHANGED_DURING_PREVIEW"
            return evidence

        after_verifier = self.preview_git_executable()
        if (
            after_verifier.get("error") is not None
            or after_verifier.get("git_executable_path")
            != verifier.get("git_executable_path")
            or after_verifier.get("git_executable_sha256")
            != verifier.get("git_executable_sha256")
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_DURING_PREVIEW"
            return evidence

        return evidence

    def diff_file(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_target_sha256: str,
        expected_head_sha256: str,
        expected_git_executable_path: str,
        expected_git_executable_sha256: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "path": expected_path,
            "diff_base": "HEAD",
            "git_command_authority": "FIXED_SINGLE_FILE_DIFF_ONLY",
            "git_arguments_model_controlled": False,
            "repository_path_model_controlled": False,
            "revision_model_controlled": False,
            "shell_used": False,
            "git_optional_locks_disabled": True,
            "git_environment_inherited_git_keys_scrubbed": True,
            "raw_stderr_returned": False,
            "max_diff_file_bytes": MAX_GIT_DIFF_FILE_BYTES,
            "max_diff_output_bytes": MAX_GIT_DIFF_OUTPUT_BYTES,
            "max_diff_lines": MAX_GIT_DIFF_LINES,
            "content_is_untrusted_data": True,
            "git_mutation_authority": False,
            "git_remote_authority": False,
        }

        preview = self.preview_diff_target(raw_path)
        preview_error = preview.get("error")
        if isinstance(preview_error, str):
            evidence.update(preview)
            return evidence
        evidence.update(
            {
                "current_target_sha256": preview["target_sha256"],
                "current_head_sha256": preview["head_sha"],
                "git_executable_path": preview["git_executable_path"],
                "git_executable_sha256": preview["git_executable_sha256"],
            }
        )

        if preview.get("path") != expected_path:
            evidence["error"] = "GIT_DIFF_PATH_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("target_sha256") != expected_target_sha256:
            evidence["error"] = "GIT_DIFF_TARGET_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("head_sha") != expected_head_sha256:
            evidence["error"] = "GIT_DIFF_HEAD_CHANGED_AFTER_PREVIEW"
            return evidence
        if (
            preview.get("git_executable_path") != expected_git_executable_path
            or preview.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"
            return evidence

        git_executable = Path(expected_git_executable_path)
        try:
            result = self._run_git(
                git_executable,
                [
                    "diff",
                    "--no-color",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--unified=3",
                    "HEAD",
                    "--",
                    expected_path,
                ],
            )
        except subprocess.TimeoutExpired:
            evidence["error"] = "GIT_DIFF_TIMEOUT"
            return evidence
        except OSError:
            evidence["error"] = "GIT_DIFF_FAILED"
            return evidence

        if result.returncode != 0:
            evidence["error"] = "GIT_DIFF_FAILED"
            return evidence
        if len(result.stdout) > MAX_GIT_DIFF_OUTPUT_BYTES:
            evidence["diff_bytes_observed"] = len(result.stdout)
            evidence["error"] = "GIT_DIFF_OUTPUT_TOO_LARGE"
            return evidence
        try:
            diff_text = result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            evidence["error"] = "GIT_DIFF_OUTPUT_ENCODING_FAILED"
            return evidence
        if "\0" in diff_text:
            evidence["error"] = "GIT_DIFF_OUTPUT_INVALID"
            return evidence

        diff_lines = len(diff_text.splitlines())
        if diff_lines > MAX_GIT_DIFF_LINES:
            evidence["diff_lines_observed"] = diff_lines
            evidence["error"] = "GIT_DIFF_LINE_LIMIT_EXCEEDED"
            return evidence
        if not diff_text:
            evidence["error"] = "GIT_DIFF_EMPTY_UNEXPECTED"
            return evidence

        after = self.preview_diff_target(raw_path)
        if after.get("error") is not None:
            evidence["state_after_error"] = after.get("error")
            evidence["error"] = "GIT_DIFF_STATE_CHANGED_DURING_READ"
            return evidence
        if (
            after.get("path") != expected_path
            or after.get("target_sha256") != expected_target_sha256
            or after.get("head_sha") != expected_head_sha256
            or after.get("git_executable_path") != expected_git_executable_path
            or after.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_DIFF_STATE_CHANGED_DURING_READ"
            return evidence

        evidence.update(
            {
                "diff_text": diff_text,
                "diff_sha256": hashlib.sha256(result.stdout).hexdigest(),
                "diff_bytes": len(result.stdout),
                "diff_lines": diff_lines,
                "has_diff": True,
                "target_unchanged": True,
                "head_unchanged": True,
                "git_executable_unchanged": True,
            }
        )
        return evidence


    def _staged_paths(
        self,
        git_executable: Path,
    ) -> tuple[list[str] | None, str | None]:
        try:
            result = self._run_git(
                git_executable,
                ["diff", "--cached", "--name-only", "-z"],
            )
        except subprocess.TimeoutExpired:
            return None, "GIT_STAGE_TIMEOUT"
        except OSError:
            return None, "GIT_STAGE_PREFLIGHT_FAILED"

        if result.returncode != 0:
            return None, "GIT_STAGE_PREFLIGHT_FAILED"
        if len(result.stdout) > MAX_GIT_STATUS_OUTPUT_BYTES:
            return None, "GIT_STATUS_OUTPUT_TOO_LARGE"
        try:
            decoded = result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None, "GIT_STATUS_OUTPUT_ENCODING_FAILED"

        paths = [item for item in decoded.split("\0") if item]
        if any(
            len(path) > MAX_GIT_STATUS_PATH_CHARS
            or any(character in path for character in ("\0", "\r", "\n"))
            for path in paths
        ):
            return None, "GIT_STATUS_OUTPUT_INVALID"
        return paths, None

    def _stage_target_status(
        self,
        git_executable: Path,
        relative_path: str,
    ) -> tuple[tuple[str, str] | None, str | None]:
        try:
            result = self._run_git(
                git_executable,
                [
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=no",
                    "--",
                    relative_path,
                ],
            )
        except subprocess.TimeoutExpired:
            return None, "GIT_STAGE_TIMEOUT"
        except OSError:
            return None, "GIT_STAGE_TARGET_STATUS_FAILED"

        if result.returncode != 0:
            return None, "GIT_STAGE_TARGET_STATUS_FAILED"
        parsed = self._parse_status(result.stdout)
        parsed_error = parsed.get("error")
        if isinstance(parsed_error, str):
            return None, parsed_error

        entries = parsed.get("entries")
        if not isinstance(entries, list) or len(entries) != 1:
            return None, "GIT_STAGE_TARGET_STATUS_FAILED"
        entry = entries[0]
        if (
            not isinstance(entry, dict)
            or entry.get("path") != relative_path
            or not isinstance(entry.get("index_status"), str)
            or not isinstance(entry.get("worktree_status"), str)
        ):
            return None, "GIT_STAGE_TARGET_STATUS_FAILED"

        return (
            str(entry["index_status"]),
            str(entry["worktree_status"]),
        ), None

    def _preview_new_file_identity(
        self,
        raw_path: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "requested_path": raw_path.strip(),
            "max_stage_new_file_bytes": MAX_GIT_STAGE_NEW_FILE_BYTES,
            "stage_content_returned": False,
            "new_untracked_file_required": True,
        }

        path, relative_path, error = self._resolve_diff_target(raw_path)
        if error is not None:
            evidence["error"] = error
            if relative_path is not None:
                evidence["path"] = relative_path
            return evidence
        assert path is not None
        assert relative_path is not None
        evidence["path"] = relative_path

        try:
            size_bytes = path.stat().st_size
            evidence["file_size_bytes"] = size_bytes
            if size_bytes > MAX_GIT_STAGE_NEW_FILE_BYTES:
                evidence["error"] = "GIT_STAGE_NEW_FILE_TOO_LARGE"
                return evidence
            payload = path.read_bytes()
        except OSError:
            evidence["error"] = "GIT_STAGE_NEW_TARGET_UNAVAILABLE"
            return evidence

        if b"\0" in payload[:8192]:
            evidence["error"] = "GIT_STAGE_NEW_BINARY_NOT_ALLOWED"
            return evidence

        target_sha256 = hashlib.sha256(payload).hexdigest()
        evidence["target_sha256"] = target_sha256

        verifier = self.preview_git_executable()
        verifier_error = verifier.get("error")
        if isinstance(verifier_error, str):
            evidence.update(verifier)
            return evidence
        evidence.update(verifier)
        git_executable = Path(str(verifier["git_executable_path"]))

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
            evidence["head_sha"] = head_sha.lower()
        except subprocess.TimeoutExpired:
            evidence["error"] = "GIT_STAGE_TIMEOUT"
            return evidence
        except (OSError, RuntimeError):
            evidence["error"] = "GIT_STAGE_NEW_PREFLIGHT_FAILED"
            return evidence

        try:
            after_payload = path.read_bytes()
        except OSError:
            evidence["error"] = "GIT_STAGE_NEW_TARGET_CHANGED_DURING_PREVIEW"
            return evidence
        if hashlib.sha256(after_payload).hexdigest() != target_sha256:
            evidence["error"] = "GIT_STAGE_NEW_TARGET_CHANGED_DURING_PREVIEW"
            return evidence

        after_verifier = self.preview_git_executable()
        if (
            after_verifier.get("error") is not None
            or after_verifier.get("git_executable_path")
            != verifier.get("git_executable_path")
            or after_verifier.get("git_executable_sha256")
            != verifier.get("git_executable_sha256")
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_DURING_PREVIEW"
            return evidence

        return evidence

    def _new_target_status(
        self,
        git_executable: Path,
        relative_path: str,
    ) -> tuple[tuple[str, str] | None, str | None]:
        try:
            result = self._run_git(
                git_executable,
                [
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                    "--",
                    relative_path,
                ],
            )
        except subprocess.TimeoutExpired:
            return None, "GIT_STAGE_TIMEOUT"
        except OSError:
            return None, "GIT_STAGE_NEW_TARGET_STATUS_FAILED"

        if result.returncode != 0:
            return None, "GIT_STAGE_NEW_TARGET_STATUS_FAILED"
        parsed = self._parse_status(result.stdout)
        parsed_error = parsed.get("error")
        if isinstance(parsed_error, str):
            return None, parsed_error

        entries = parsed.get("entries")
        if not isinstance(entries, list) or len(entries) != 1:
            return None, "GIT_STAGE_NEW_TARGET_STATUS_FAILED"
        entry = entries[0]
        if (
            not isinstance(entry, dict)
            or entry.get("path") != relative_path
            or not isinstance(entry.get("index_status"), str)
            or not isinstance(entry.get("worktree_status"), str)
        ):
            return None, "GIT_STAGE_NEW_TARGET_STATUS_FAILED"

        return (
            str(entry["index_status"]),
            str(entry["worktree_status"]),
        ), None

    def preview_stage_new_target(self, raw_path: str) -> dict[str, object]:
        evidence = self._preview_new_file_identity(raw_path)
        evidence["empty_index_required"] = True
        evidence["git_mutation_authority"] = "SINGLE_NEW_FILE_STAGE_ONLY"
        evidence["git_remote_authority"] = False
        evidence["commit_authority"] = False

        if evidence.get("error") is not None:
            return evidence

        git_path = evidence.get("git_executable_path")
        relative_path = evidence.get("path")
        if not isinstance(git_path, str) or not isinstance(relative_path, str):
            evidence["error"] = "GIT_STAGE_NEW_PREFLIGHT_FAILED"
            return evidence
        git_executable = Path(git_path)

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None:
            evidence["error"] = staged_error
            return evidence
        assert staged_paths is not None
        evidence["staged_paths_observed"] = len(staged_paths)
        if staged_paths:
            evidence["error"] = "GIT_STAGE_NEW_REQUIRES_EMPTY_INDEX"
            return evidence

        target_status, status_error = self._new_target_status(
            git_executable,
            relative_path,
        )
        if status_error is not None:
            evidence["error"] = status_error
            return evidence
        assert target_status is not None
        index_status, worktree_status = target_status
        evidence["target_index_status"] = index_status
        evidence["target_worktree_status"] = worktree_status
        if index_status != "?" or worktree_status != "?":
            evidence["error"] = "GIT_STAGE_NEW_TARGET_NOT_UNTRACKED"
            return evidence

        evidence["index_empty"] = True
        return evidence

    def _rollback_stage_new_target(
        self,
        git_executable: Path,
        relative_path: str,
    ) -> bool:
        try:
            result = self._run_git_mutating(
                git_executable,
                ["reset", "--quiet", "HEAD", "--", relative_path],
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None or staged_paths != []:
            return False

        target_status, status_error = self._new_target_status(
            git_executable,
            relative_path,
        )
        return (
            status_error is None
            and target_status is not None
            and target_status[0] == "?"
            and target_status[1] == "?"
        )

    def stage_new_file(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_target_sha256: str,
        expected_head_sha256: str,
        expected_git_executable_path: str,
        expected_git_executable_sha256: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "path": expected_path,
            "git_command_authority": "FIXED_SINGLE_NEW_FILE_STAGE_ONLY",
            "git_arguments_model_controlled": False,
            "repository_path_model_controlled": False,
            "revision_model_controlled": False,
            "shell_used": False,
            "git_environment_inherited_git_keys_scrubbed": True,
            "git_optional_locks_disabled": False,
            "raw_stdout_returned": False,
            "raw_stderr_returned": False,
            "git_mutation_authority": "INDEX_ONLY_SINGLE_NEW_FILE",
            "git_remote_authority": False,
            "commit_authority": False,
            "rollback_authority": "SAME_PATH_RESET_ONLY_ON_FAILURE",
        }

        preview = self.preview_stage_new_target(raw_path)
        preview_error = preview.get("error")
        if isinstance(preview_error, str):
            evidence.update(preview)
            return evidence

        if preview.get("path") != expected_path:
            evidence["error"] = "GIT_STAGE_NEW_PATH_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("target_sha256") != expected_target_sha256:
            evidence["error"] = "GIT_STAGE_NEW_TARGET_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("head_sha") != expected_head_sha256:
            evidence["error"] = "GIT_STAGE_NEW_HEAD_CHANGED_AFTER_PREVIEW"
            return evidence
        if (
            preview.get("git_executable_path") != expected_git_executable_path
            or preview.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("index_empty") is not True:
            evidence["error"] = "GIT_STAGE_NEW_REQUIRES_EMPTY_INDEX"
            return evidence

        git_executable = Path(expected_git_executable_path)

        try:
            result = self._run_git_mutating(
                git_executable,
                ["add", "--", expected_path],
            )
        except subprocess.TimeoutExpired:
            evidence["rollback_verified"] = self._rollback_stage_new_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_NEW_TIMEOUT"
            return evidence
        except OSError:
            evidence["rollback_verified"] = self._rollback_stage_new_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_NEW_FAILED"
            return evidence

        if result.returncode != 0:
            evidence["rollback_verified"] = self._rollback_stage_new_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_NEW_FAILED"
            return evidence

        after = self._preview_new_file_identity(raw_path)
        after_verifier = self.preview_git_executable()
        staged_paths, staged_error = self._staged_paths(git_executable)
        target_status, status_error = self._new_target_status(
            git_executable,
            expected_path,
        )

        postcondition_ok = (
            after.get("error") is None
            and after.get("path") == expected_path
            and after.get("target_sha256") == expected_target_sha256
            and after.get("head_sha") == expected_head_sha256
            and after.get("git_executable_path") == expected_git_executable_path
            and after.get("git_executable_sha256")
            == expected_git_executable_sha256
            and after_verifier.get("error") is None
            and after_verifier.get("git_executable_path")
            == expected_git_executable_path
            and after_verifier.get("git_executable_sha256")
            == expected_git_executable_sha256
            and staged_error is None
            and staged_paths == [expected_path]
            and status_error is None
            and target_status == ("A", " ")
        )

        if not postcondition_ok:
            evidence["post_stage_staged_paths"] = staged_paths
            evidence["post_stage_target_status"] = target_status
            evidence["post_stage_state_error"] = after.get("error")
            evidence["rollback_verified"] = self._rollback_stage_new_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_NEW_POSTCONDITION_FAILED"
            return evidence

        evidence.update(
            {
                "staged_path": expected_path,
                "staged_paths_observed": 1,
                "target_index_status": "A",
                "target_worktree_status": " ",
                "index_only_mutation_verified": True,
                "target_unchanged": True,
                "head_unchanged": True,
                "git_executable_unchanged": True,
            }
        )
        return evidence

    def preview_stage_target(self, raw_path: str) -> dict[str, object]:
        evidence = self.preview_diff_target(raw_path)
        evidence["max_stage_file_bytes"] = MAX_GIT_STAGE_FILE_BYTES
        evidence["stage_content_returned"] = False
        evidence["tracked_existing_file_required"] = True
        evidence["empty_index_required"] = True
        evidence["git_mutation_authority"] = "SINGLE_TRACKED_FILE_STAGE_ONLY"
        evidence["git_remote_authority"] = False
        evidence["commit_authority"] = False

        if evidence.get("error") is not None:
            return evidence

        git_path = evidence.get("git_executable_path")
        relative_path = evidence.get("path")
        if not isinstance(git_path, str) or not isinstance(relative_path, str):
            evidence["error"] = "GIT_STAGE_PREFLIGHT_FAILED"
            return evidence
        git_executable = Path(git_path)

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None:
            evidence["error"] = staged_error
            return evidence
        assert staged_paths is not None
        evidence["staged_paths_observed"] = len(staged_paths)
        if staged_paths:
            evidence["error"] = "GIT_STAGE_REQUIRES_EMPTY_INDEX"
            return evidence

        target_status, status_error = self._stage_target_status(
            git_executable,
            relative_path,
        )
        if status_error is not None:
            evidence["error"] = status_error
            return evidence
        assert target_status is not None
        index_status, worktree_status = target_status
        evidence["target_index_status"] = index_status
        evidence["target_worktree_status"] = worktree_status
        if index_status != " " or worktree_status != "M":
            evidence["error"] = "GIT_STAGE_TARGET_NOT_UNSTAGED_MODIFICATION"
            return evidence

        evidence["index_empty"] = True
        return evidence

    def _rollback_stage_target(
        self,
        git_executable: Path,
        relative_path: str,
    ) -> bool:
        try:
            result = self._run_git_mutating(
                git_executable,
                ["reset", "--quiet", "HEAD", "--", relative_path],
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None or staged_paths != []:
            return False

        target_status, status_error = self._stage_target_status(
            git_executable,
            relative_path,
        )
        return (
            status_error is None
            and target_status is not None
            and target_status[0] == " "
            and target_status[1] == "M"
        )

    def stage_file(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_target_sha256: str,
        expected_head_sha256: str,
        expected_git_executable_path: str,
        expected_git_executable_sha256: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "path": expected_path,
            "git_command_authority": "FIXED_SINGLE_TRACKED_FILE_STAGE_ONLY",
            "git_arguments_model_controlled": False,
            "repository_path_model_controlled": False,
            "revision_model_controlled": False,
            "shell_used": False,
            "git_environment_inherited_git_keys_scrubbed": True,
            "git_optional_locks_disabled": False,
            "raw_stdout_returned": False,
            "raw_stderr_returned": False,
            "git_mutation_authority": "INDEX_ONLY_SINGLE_TRACKED_FILE",
            "git_remote_authority": False,
            "commit_authority": False,
            "rollback_authority": "SAME_PATH_ONLY_ON_FAILURE",
        }

        preview = self.preview_stage_target(raw_path)
        preview_error = preview.get("error")
        if isinstance(preview_error, str):
            evidence.update(preview)
            return evidence

        if preview.get("path") != expected_path:
            evidence["error"] = "GIT_STAGE_PATH_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("target_sha256") != expected_target_sha256:
            evidence["error"] = "GIT_STAGE_TARGET_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("head_sha") != expected_head_sha256:
            evidence["error"] = "GIT_STAGE_HEAD_CHANGED_AFTER_PREVIEW"
            return evidence
        if (
            preview.get("git_executable_path") != expected_git_executable_path
            or preview.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("index_empty") is not True:
            evidence["error"] = "GIT_STAGE_REQUIRES_EMPTY_INDEX"
            return evidence

        git_executable = Path(expected_git_executable_path)

        try:
            result = self._run_git_mutating(
                git_executable,
                ["add", "--", expected_path],
            )
        except subprocess.TimeoutExpired:
            evidence["rollback_verified"] = self._rollback_stage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_TIMEOUT"
            return evidence
        except OSError:
            evidence["rollback_verified"] = self._rollback_stage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_FAILED"
            return evidence

        if result.returncode != 0:
            evidence["rollback_verified"] = self._rollback_stage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_FAILED"
            return evidence

        after = self.preview_diff_target(raw_path)
        after_verifier = self.preview_git_executable()
        staged_paths, staged_error = self._staged_paths(git_executable)
        target_status, status_error = self._stage_target_status(
            git_executable,
            expected_path,
        )

        postcondition_ok = (
            after.get("error") is None
            and after.get("path") == expected_path
            and after.get("target_sha256") == expected_target_sha256
            and after.get("head_sha") == expected_head_sha256
            and after.get("git_executable_path") == expected_git_executable_path
            and after.get("git_executable_sha256")
            == expected_git_executable_sha256
            and after_verifier.get("error") is None
            and after_verifier.get("git_executable_path")
            == expected_git_executable_path
            and after_verifier.get("git_executable_sha256")
            == expected_git_executable_sha256
            and staged_error is None
            and staged_paths == [expected_path]
            and status_error is None
            and target_status == ("M", " ")
        )

        if not postcondition_ok:
            evidence["post_stage_staged_paths"] = staged_paths
            evidence["post_stage_target_status"] = target_status
            evidence["post_stage_state_error"] = after.get("error")
            evidence["rollback_verified"] = self._rollback_stage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_STAGE_POSTCONDITION_FAILED"
            return evidence

        evidence.update(
            {
                "staged_path": expected_path,
                "staged_paths_observed": 1,
                "target_index_status": "M",
                "target_worktree_status": " ",
                "index_only_mutation_verified": True,
                "target_unchanged": True,
                "head_unchanged": True,
                "git_executable_unchanged": True,
            }
        )
        return evidence

    def preview_unstage_target(self, raw_path: str) -> dict[str, object]:
        evidence = self.preview_diff_target(raw_path)
        evidence["max_unstage_file_bytes"] = MAX_GIT_UNSTAGE_FILE_BYTES
        evidence["unstage_content_returned"] = False
        evidence["tracked_existing_file_required"] = True
        evidence["single_staged_target_required"] = True
        evidence["git_mutation_authority"] = "SINGLE_TRACKED_FILE_UNSTAGE_ONLY"
        evidence["git_remote_authority"] = False
        evidence["commit_authority"] = False

        if evidence.get("error") is not None:
            return evidence

        git_path = evidence.get("git_executable_path")
        relative_path = evidence.get("path")
        if not isinstance(git_path, str) or not isinstance(relative_path, str):
            evidence["error"] = "GIT_UNSTAGE_PREFLIGHT_FAILED"
            return evidence
        git_executable = Path(git_path)

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None:
            evidence["error"] = staged_error
            return evidence
        assert staged_paths is not None
        evidence["staged_paths_observed"] = len(staged_paths)
        if staged_paths != [relative_path]:
            evidence["error"] = "GIT_UNSTAGE_REQUIRES_ONLY_TARGET_STAGED"
            return evidence

        target_status, status_error = self._stage_target_status(
            git_executable,
            relative_path,
        )
        if status_error is not None:
            evidence["error"] = status_error
            return evidence
        assert target_status is not None
        index_status, worktree_status = target_status
        evidence["target_index_status"] = index_status
        evidence["target_worktree_status"] = worktree_status
        if index_status != "M" or worktree_status != " ":
            evidence["error"] = "GIT_UNSTAGE_TARGET_NOT_STAGED_MODIFICATION"
            return evidence

        evidence["index_contains_only_target"] = True
        return evidence

    def _rollback_unstage_target(
        self,
        git_executable: Path,
        relative_path: str,
    ) -> bool:
        try:
            result = self._run_git_mutating(
                git_executable,
                ["add", "--", relative_path],
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False

        staged_paths, staged_error = self._staged_paths(git_executable)
        if staged_error is not None or staged_paths != [relative_path]:
            return False

        target_status, status_error = self._stage_target_status(
            git_executable,
            relative_path,
        )
        return (
            status_error is None
            and target_status is not None
            and target_status[0] == "M"
            and target_status[1] == " "
        )

    def unstage_file(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_target_sha256: str,
        expected_head_sha256: str,
        expected_git_executable_path: str,
        expected_git_executable_sha256: str,
    ) -> dict[str, object]:
        evidence: dict[str, object] = {
            "repository_root": str(self._repository_root),
            "path": expected_path,
            "git_command_authority": "FIXED_SINGLE_TRACKED_FILE_UNSTAGE_ONLY",
            "git_arguments_model_controlled": False,
            "repository_path_model_controlled": False,
            "revision_model_controlled": False,
            "shell_used": False,
            "git_environment_inherited_git_keys_scrubbed": True,
            "git_optional_locks_disabled": False,
            "raw_stdout_returned": False,
            "raw_stderr_returned": False,
            "git_mutation_authority": "INDEX_ONLY_SINGLE_TRACKED_FILE_UNSTAGE",
            "git_remote_authority": False,
            "commit_authority": False,
            "rollback_authority": "SAME_PATH_RESTAGE_ONLY_ON_FAILURE",
        }

        preview = self.preview_unstage_target(raw_path)
        preview_error = preview.get("error")
        if isinstance(preview_error, str):
            evidence.update(preview)
            return evidence

        if preview.get("path") != expected_path:
            evidence["error"] = "GIT_UNSTAGE_PATH_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("target_sha256") != expected_target_sha256:
            evidence["error"] = "GIT_UNSTAGE_TARGET_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("head_sha") != expected_head_sha256:
            evidence["error"] = "GIT_UNSTAGE_HEAD_CHANGED_AFTER_PREVIEW"
            return evidence
        if (
            preview.get("git_executable_path") != expected_git_executable_path
            or preview.get("git_executable_sha256")
            != expected_git_executable_sha256
        ):
            evidence["error"] = "GIT_EXECUTABLE_CHANGED_AFTER_PREVIEW"
            return evidence
        if preview.get("index_contains_only_target") is not True:
            evidence["error"] = "GIT_UNSTAGE_REQUIRES_ONLY_TARGET_STAGED"
            return evidence

        git_executable = Path(expected_git_executable_path)

        try:
            result = self._run_git_mutating(
                git_executable,
                ["reset", "--quiet", "HEAD", "--", expected_path],
            )
        except subprocess.TimeoutExpired:
            evidence["rollback_verified"] = self._rollback_unstage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_UNSTAGE_TIMEOUT"
            return evidence
        except OSError:
            evidence["rollback_verified"] = self._rollback_unstage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_UNSTAGE_FAILED"
            return evidence

        if result.returncode != 0:
            evidence["rollback_verified"] = self._rollback_unstage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_UNSTAGE_FAILED"
            return evidence

        after = self.preview_diff_target(raw_path)
        after_verifier = self.preview_git_executable()
        staged_paths, staged_error = self._staged_paths(git_executable)
        target_status, status_error = self._stage_target_status(
            git_executable,
            expected_path,
        )

        postcondition_ok = (
            after.get("error") is None
            and after.get("path") == expected_path
            and after.get("target_sha256") == expected_target_sha256
            and after.get("head_sha") == expected_head_sha256
            and after.get("git_executable_path") == expected_git_executable_path
            and after.get("git_executable_sha256")
            == expected_git_executable_sha256
            and after_verifier.get("error") is None
            and after_verifier.get("git_executable_path")
            == expected_git_executable_path
            and after_verifier.get("git_executable_sha256")
            == expected_git_executable_sha256
            and staged_error is None
            and staged_paths == []
            and status_error is None
            and target_status == (" ", "M")
        )

        if not postcondition_ok:
            evidence["post_unstage_staged_paths"] = staged_paths
            evidence["post_unstage_target_status"] = target_status
            evidence["post_unstage_state_error"] = after.get("error")
            evidence["rollback_verified"] = self._rollback_unstage_target(
                git_executable,
                expected_path,
            )
            evidence["error"] = "GIT_UNSTAGE_POSTCONDITION_FAILED"
            return evidence

        evidence.update(
            {
                "unstaged_path": expected_path,
                "staged_paths_observed": 0,
                "target_index_status": " ",
                "target_worktree_status": "M",
                "index_only_mutation_verified": True,
                "target_unchanged": True,
                "head_unchanged": True,
                "git_executable_unchanged": True,
            }
        )
        return evidence

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
