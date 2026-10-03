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
