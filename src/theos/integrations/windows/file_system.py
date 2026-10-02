from __future__ import annotations

import codecs
import ctypes
import difflib
import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path

MAX_DIRECTORY_ENTRIES = 30
MAX_FIND_RESULTS = 20
MAX_FIND_DEPTH = 4
MAX_TEXT_SEARCH_QUERY_CHARS = 120
MAX_TEXT_SEARCH_RESULTS = 20
MAX_TEXT_SEARCH_DEPTH = 4
MAX_TEXT_SEARCH_FILES = 64
MAX_TEXT_SEARCH_BYTES_PER_FILE = 64 * 1024
MAX_TEXT_SEARCH_TOTAL_BYTES = 512 * 1024
MAX_TEXT_SEARCH_SNIPPET_CHARS = 240
MAX_READ_BYTES = 16 * 1024
MAX_TEXT_LINE_START = 1_000_000
MAX_TEXT_LINE_RANGE_LINES = 40
MAX_TEXT_LINE_RANGE_SCAN_BYTES = 256 * 1024
MAX_TEXT_LINE_RANGE_OUTPUT_BYTES = 16 * 1024
MAX_WRITE_BYTES = 16 * 1024
MAX_LITERAL_REPLACE_FILE_BYTES = 256 * 1024
MAX_LITERAL_REPLACE_TEXT_CHARS = 1024
MAX_WRITE_PREVIEW_CHARS = 3500
MAX_COPY_ENTRIES = 256
MAX_COPY_BYTES = 64 * 1024 * 1024

_FO_DELETE = 0x0003
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400


def _recycle_with_shell(path: Path) -> tuple[int, bool]:
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = _FO_DELETE
    operation.pFrom = f"{path}\0\0"
    operation.pTo = None
    operation.fFlags = (
        _FOF_SILENT
        | _FOF_NOCONFIRMATION
        | _FOF_ALLOWUNDO
        | _FOF_NOERRORUI
    )
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    return int(result), bool(operation.fAnyOperationsAborted)


class WindowsFileSystemAdapter:
    """Bounded Windows filesystem inspection, search, open, read, and write primitives."""

    @staticmethod
    def resolve(raw_path: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(raw_path.strip()))
        return Path(expanded).resolve(strict=False)

    def inspect(self, raw_path: str) -> dict[str, object]:
        path = self.resolve(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
        }
        if not path.exists():
            return evidence

        stat = path.stat()
        evidence["kind"] = "directory" if path.is_dir() else "file"
        evidence["modified_utc"] = datetime.fromtimestamp(
            stat.st_mtime,
            tz=UTC,
        ).isoformat()

        if path.is_file():
            evidence["size_bytes"] = stat.st_size
            evidence["suffix"] = path.suffix
            return evidence

        entries: list[dict[str, object]] = []
        truncated = False
        try:
            children = sorted(
                path.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.casefold()),
            )
            for index, child in enumerate(children):
                if index >= MAX_DIRECTORY_ENTRIES:
                    truncated = True
                    break
                entries.append(
                    {
                        "name": child.name,
                        "kind": "directory" if child.is_dir() else "file",
                    }
                )
        except PermissionError:
            evidence["listing_error"] = "ACCESS_DENIED"
            return evidence

        evidence["entries"] = entries
        evidence["entries_truncated"] = truncated
        return evidence

    def find(
        self,
        raw_root: str,
        query: str,
        *,
        max_results: int = MAX_FIND_RESULTS,
        max_depth: int = MAX_FIND_DEPTH,
    ) -> dict[str, object]:
        root = self.resolve(raw_root)
        normalized_query = query.strip().casefold()
        evidence: dict[str, object] = {
            "root": str(root),
            "query": query.strip(),
            "exists": root.exists(),
            "is_directory": root.is_dir(),
            "matches": [],
            "truncated": False,
            "scanned_directories": 0,
            "access_errors": 0,
        }
        if not root.exists() or not root.is_dir() or not normalized_query:
            return evidence

        matches: list[dict[str, object]] = []
        scanned_directories = 0
        access_errors = 0
        root_depth = len(root.parts)

        def onerror(_error: OSError) -> None:
            nonlocal access_errors
            access_errors += 1

        for current, directories, filenames in os.walk(root, topdown=True, onerror=onerror):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            scanned_directories += 1

            directories.sort(key=str.casefold)
            filenames.sort(key=str.casefold)

            if depth >= max_depth:
                directories[:] = []

            for name, kind in (
                *((name, "directory") for name in directories),
                *((name, "file") for name in filenames),
            ):
                if normalized_query not in name.casefold():
                    continue
                matches.append(
                    {
                        "path": str(current_path / name),
                        "name": name,
                        "kind": kind,
                    }
                )
                if len(matches) >= max_results:
                    evidence["matches"] = matches
                    evidence["truncated"] = True
                    evidence["scanned_directories"] = scanned_directories
                    evidence["access_errors"] = access_errors
                    return evidence

        evidence["matches"] = matches
        evidence["scanned_directories"] = scanned_directories
        evidence["access_errors"] = access_errors
        return evidence

    def search_text(
        self,
        raw_root: str,
        query: str,
        *,
        should_skip: Callable[[Path], bool] | None = None,
        max_results: int = MAX_TEXT_SEARCH_RESULTS,
        max_depth: int = MAX_TEXT_SEARCH_DEPTH,
        max_files: int = MAX_TEXT_SEARCH_FILES,
        max_bytes_per_file: int = MAX_TEXT_SEARCH_BYTES_PER_FILE,
        max_total_bytes: int = MAX_TEXT_SEARCH_TOTAL_BYTES,
    ) -> dict[str, object]:
        if max_results < 1 or max_results > MAX_TEXT_SEARCH_RESULTS:
            raise ValueError("invalid max_results")
        if max_depth < 0 or max_depth > MAX_TEXT_SEARCH_DEPTH:
            raise ValueError("invalid max_depth")
        if max_files < 1 or max_files > MAX_TEXT_SEARCH_FILES:
            raise ValueError("invalid max_files")
        if (
            max_bytes_per_file < 1
            or max_bytes_per_file > MAX_TEXT_SEARCH_BYTES_PER_FILE
        ):
            raise ValueError("invalid max_bytes_per_file")
        if max_total_bytes < 1 or max_total_bytes > MAX_TEXT_SEARCH_TOTAL_BYTES:
            raise ValueError("invalid max_total_bytes")

        normalized_query = query.strip()
        if (
            not normalized_query
            or len(normalized_query) > MAX_TEXT_SEARCH_QUERY_CHARS
            or any(character in normalized_query for character in ("\0", "\r", "\n"))
        ):
            raise ValueError("invalid text search query")

        root = self.resolve(raw_root)
        evidence: dict[str, object] = {
            "root": str(root),
            "query": normalized_query,
            "match_mode": "casefold_literal_line_substring",
            "exists": root.exists(),
            "is_directory": root.is_dir(),
            "max_results": max_results,
            "max_depth": max_depth,
            "max_files": max_files,
            "max_bytes_per_file": max_bytes_per_file,
            "max_total_bytes": max_total_bytes,
            "max_snippet_chars": MAX_TEXT_SEARCH_SNIPPET_CHARS,
            "matches": [],
            "files_scanned": 0,
            "bytes_scanned": 0,
            "access_errors": 0,
            "skipped_binary_files": 0,
            "skipped_sensitive_files": 0,
            "skipped_link_entries": 0,
            "partial_files": 0,
            "depth_limited": False,
            "result_limit_reached": False,
            "file_limit_reached": False,
            "byte_limit_reached": False,
            "content_is_untrusted_data": True,
            "complete": False,
        }
        if not root.exists() or not root.is_dir():
            return evidence

        matches: list[dict[str, object]] = []
        files_scanned = 0
        bytes_scanned = 0
        access_errors = 0
        skipped_binary_files = 0
        skipped_sensitive_files = 0
        skipped_link_entries = 0
        partial_files = 0
        depth_limited = False
        result_limit_reached = False
        file_limit_reached = False
        byte_limit_reached = False
        root_depth = len(root.parts)
        query_casefold = normalized_query.casefold()

        def onerror(_error: OSError) -> None:
            nonlocal access_errors
            access_errors += 1

        stop = False
        for current, directories, filenames in os.walk(
            root,
            topdown=True,
            onerror=onerror,
            followlinks=False,
        ):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth

            directories.sort(key=str.casefold)
            filenames.sort(key=str.casefold)

            if depth >= max_depth:
                if directories:
                    depth_limited = True
                directories[:] = []
            else:
                retained_directories: list[str] = []
                for name in directories:
                    child = current_path / name
                    try:
                        link_like = self._is_link_like(child)
                    except OSError:
                        access_errors += 1
                        continue
                    if link_like:
                        skipped_link_entries += 1
                        continue
                    retained_directories.append(name)
                directories[:] = retained_directories

            for name in filenames:
                if len(matches) >= max_results:
                    result_limit_reached = True
                    stop = True
                    break
                if files_scanned >= max_files:
                    file_limit_reached = True
                    stop = True
                    break
                if bytes_scanned >= max_total_bytes:
                    byte_limit_reached = True
                    stop = True
                    break

                path = current_path / name
                try:
                    if self._is_link_like(path):
                        skipped_link_entries += 1
                        continue
                except OSError:
                    access_errors += 1
                    continue

                if should_skip is not None and should_skip(path):
                    skipped_sensitive_files += 1
                    continue

                remaining_total = max_total_bytes - bytes_scanned
                if remaining_total <= 0:
                    byte_limit_reached = True
                    stop = True
                    break
                read_limit = min(max_bytes_per_file, remaining_total)

                try:
                    size_bytes = path.stat().st_size
                    with path.open("rb") as handle:
                        raw = handle.read(read_limit + 1)
                except OSError:
                    access_errors += 1
                    continue

                files_scanned += 1
                chunk = raw[:read_limit]
                bytes_scanned += len(chunk)
                file_partial = len(raw) > read_limit or size_bytes > len(chunk)
                if file_partial:
                    partial_files += 1

                encoding = self._detect_text_encoding(chunk)
                if encoding is None:
                    skipped_binary_files += 1
                    continue
                try:
                    content = (
                        chunk.decode(encoding)
                        .replace("\r\n", "\n")
                        .replace("\r", "\n")
                    )
                except UnicodeDecodeError:
                    skipped_binary_files += 1
                    continue

                for line_number, line in enumerate(content.split("\n"), start=1):
                    if query_casefold not in line.casefold():
                        continue
                    snippet = line.strip().replace("\t", " ")
                    snippet_truncated = len(snippet) > MAX_TEXT_SEARCH_SNIPPET_CHARS
                    if snippet_truncated:
                        snippet = (
                            snippet[: MAX_TEXT_SEARCH_SNIPPET_CHARS - 1] + "…"
                        )
                    matches.append(
                        {
                            "path": str(path),
                            "relative_path": path.relative_to(root).as_posix(),
                            "line_number": line_number,
                            "snippet": snippet,
                            "snippet_truncated": snippet_truncated,
                            "file_prefix_only": file_partial,
                        }
                    )
                    if len(matches) >= max_results:
                        result_limit_reached = True
                        stop = True
                        break

                if stop:
                    break
                if bytes_scanned >= max_total_bytes:
                    byte_limit_reached = True
                    stop = True
                    break

            if stop:
                break

        complete = not any(
            (
                access_errors,
                skipped_sensitive_files,
                skipped_link_entries,
                partial_files,
                depth_limited,
                result_limit_reached,
                file_limit_reached,
                byte_limit_reached,
            )
        )
        evidence.update(
            {
                "matches": matches,
                "files_scanned": files_scanned,
                "bytes_scanned": bytes_scanned,
                "access_errors": access_errors,
                "skipped_binary_files": skipped_binary_files,
                "skipped_sensitive_files": skipped_sensitive_files,
                "skipped_link_entries": skipped_link_entries,
                "partial_files": partial_files,
                "depth_limited": depth_limited,
                "result_limit_reached": result_limit_reached,
                "file_limit_reached": file_limit_reached,
                "byte_limit_reached": byte_limit_reached,
                "complete": complete,
            }
        )
        return evidence

    def open_path(self, raw_path: str) -> dict[str, object]:
        path = self.resolve(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
        }
        if not path.exists():
            return evidence

        os.startfile(str(path))
        evidence["kind"] = "directory" if path.is_dir() else "file"
        evidence["shell_request_submitted"] = True
        return evidence

    def read_text(
        self,
        raw_path: str,
        *,
        max_bytes: int = MAX_READ_BYTES,
    ) -> dict[str, object]:
        if max_bytes < 1 or max_bytes > MAX_READ_BYTES:
            raise ValueError(f"max_bytes must be between 1 and {MAX_READ_BYTES}")

        path = self.resolve(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "max_bytes": max_bytes,
        }
        if not path.exists():
            return evidence

        evidence["is_file"] = path.is_file()
        if not path.is_file():
            return evidence

        size_bytes = path.stat().st_size
        evidence["size_bytes"] = size_bytes

        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)

        truncated = len(raw) > max_bytes
        chunk = raw[:max_bytes]
        evidence["bytes_read"] = len(chunk)
        evidence["truncated"] = truncated or size_bytes > len(chunk)

        encoding = self._detect_text_encoding(chunk)
        if encoding is None:
            evidence["text"] = False
            evidence["error"] = "BINARY_OR_UNSUPPORTED_ENCODING"
            return evidence

        try:
            content = chunk.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            evidence["text"] = False
            evidence["error"] = "BINARY_OR_UNSUPPORTED_ENCODING"
            return evidence

        evidence["text"] = True
        evidence["encoding"] = encoding
        evidence["content"] = content
        evidence["content_is_untrusted_data"] = True
        evidence["line_count_in_chunk"] = content.count("\n") + (1 if content else 0)
        return evidence

    def read_text_lines(
        self,
        raw_path: str,
        start_line: int,
        max_lines: int,
        *,
        max_scan_bytes: int = MAX_TEXT_LINE_RANGE_SCAN_BYTES,
        max_output_bytes: int = MAX_TEXT_LINE_RANGE_OUTPUT_BYTES,
    ) -> dict[str, object]:
        if (
            start_line < 1
            or start_line > MAX_TEXT_LINE_START
            or max_lines < 1
            or max_lines > MAX_TEXT_LINE_RANGE_LINES
        ):
            raise ValueError("invalid text line range")
        if max_scan_bytes < 1 or max_scan_bytes > MAX_TEXT_LINE_RANGE_SCAN_BYTES:
            raise ValueError("invalid max_scan_bytes")
        if max_output_bytes < 1 or max_output_bytes > MAX_TEXT_LINE_RANGE_OUTPUT_BYTES:
            raise ValueError("invalid max_output_bytes")

        path = self.resolve(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "start_line": start_line,
            "max_lines": max_lines,
            "max_scan_bytes": max_scan_bytes,
            "max_output_bytes": max_output_bytes,
            "content_is_untrusted_data": True,
        }
        if not path.exists():
            return evidence

        evidence["is_file"] = path.is_file()
        if not path.is_file():
            return evidence

        size_bytes = path.stat().st_size
        evidence["size_bytes"] = size_bytes

        with path.open("rb") as handle:
            raw = handle.read(max_scan_bytes + 1)

        scanned = raw[:max_scan_bytes]
        scan_truncated = len(raw) > max_scan_bytes or size_bytes > len(scanned)
        evidence["bytes_scanned"] = len(scanned)
        evidence["scan_truncated"] = scan_truncated

        encoding = self._detect_text_encoding(scanned)
        if encoding is None:
            evidence["text"] = False
            evidence["error"] = "BINARY_OR_UNSUPPORTED_ENCODING"
            return evidence

        try:
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            content = decoder.decode(scanned, final=not scan_truncated)
        except UnicodeDecodeError:
            evidence["text"] = False
            evidence["error"] = "BINARY_OR_UNSUPPORTED_ENCODING"
            return evidence

        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized:
            complete_lines: list[str] = []
        else:
            complete_lines = normalized.split("\n")
            if normalized.endswith("\n") or scan_truncated and complete_lines:
                complete_lines.pop()

        last_complete_line_scanned = len(complete_lines)
        evidence["text"] = True
        evidence["encoding"] = encoding
        evidence["last_complete_line_scanned"] = last_complete_line_scanned
        evidence["start_line_reached"] = start_line <= last_complete_line_scanned

        if start_line > last_complete_line_scanned:
            evidence["lines"] = []
            evidence["bytes_returned"] = 0
            evidence["output_truncated"] = False
            evidence["range_complete"] = not scan_truncated
            if not scan_truncated:
                evidence["total_lines"] = last_complete_line_scanned
            return evidence

        requested = complete_lines[
            start_line - 1 : start_line - 1 + max_lines
        ]
        returned: list[dict[str, object]] = []
        bytes_returned = 0
        output_truncated = False

        for offset, line in enumerate(requested):
            remaining = max_output_bytes - bytes_returned
            if remaining <= 0:
                output_truncated = True
                break

            encoded = line.encode("utf-8")
            text_truncated = len(encoded) > remaining
            if text_truncated:
                piece = encoded[:remaining].decode("utf-8", errors="ignore")
            else:
                piece = line

            returned.append(
                {
                    "line_number": start_line + offset,
                    "text": piece,
                    "text_truncated": text_truncated,
                }
            )
            bytes_returned += len(piece.encode("utf-8"))

            if text_truncated:
                output_truncated = True
                break

        source_range_complete = (
            len(requested) == max_lines or not scan_truncated
        )
        evidence["lines"] = returned
        evidence["bytes_returned"] = bytes_returned
        evidence["output_truncated"] = output_truncated
        evidence["range_complete"] = source_range_complete and not output_truncated
        if returned:
            evidence["end_line_returned"] = returned[-1]["line_number"]
        if not scan_truncated:
            evidence["total_lines"] = last_complete_line_scanned
        return evidence

    def preview_text_write(
        self,
        raw_path: str,
        content: str,
    ) -> dict[str, object]:
        path = self.resolve(raw_path)
        normalized = self._normalize_text(content)
        new_bytes = normalized.encode("utf-8")
        new_sha256 = hashlib.sha256(new_bytes).hexdigest()

        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "new_bytes": len(new_bytes),
            "new_sha256": new_sha256,
            "allowed": False,
        }

        if len(new_bytes) > MAX_WRITE_BYTES:
            evidence["error"] = "CONTENT_TOO_LARGE"
            return evidence

        parent = path.parent
        evidence["parent"] = str(parent)
        evidence["parent_exists"] = parent.exists()
        evidence["parent_is_directory"] = parent.is_dir()
        if not parent.exists() or not parent.is_dir():
            evidence["error"] = "PARENT_NOT_DIRECTORY"
            return evidence

        before = ""
        before_sha256: str | None = None
        if path.exists():
            if not path.is_file():
                evidence["error"] = "PATH_NOT_FILE"
                return evidence

            size_bytes = path.stat().st_size
            evidence["old_bytes"] = size_bytes
            if size_bytes > MAX_WRITE_BYTES:
                evidence["error"] = "EXISTING_FILE_TOO_LARGE"
                return evidence

            raw_before = path.read_bytes()
            before_sha256 = hashlib.sha256(raw_before).hexdigest()
            encoding = self._detect_text_encoding(raw_before)
            if encoding is None:
                evidence["error"] = "EXISTING_FILE_NOT_TEXT"
                return evidence

            try:
                before = (
                    raw_before.decode(encoding)
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                )
            except UnicodeDecodeError:
                evidence["error"] = "EXISTING_FILE_NOT_TEXT"
                return evidence

        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                normalized.splitlines(keepends=True),
                fromfile=f"antes/{path.name}",
                tofile=f"depois/{path.name}",
                n=3,
            )
        )
        if len(diff) > MAX_WRITE_PREVIEW_CHARS:
            diff = (
                diff[:MAX_WRITE_PREVIEW_CHARS]
                + "\n... prévia truncada pelo limite local ..."
            )
            evidence["preview_truncated"] = True
        else:
            evidence["preview_truncated"] = False

        evidence["allowed"] = True
        evidence["before_sha256"] = before_sha256
        evidence["changed"] = before != normalized
        evidence["diff"] = diff
        evidence["mode"] = "replace" if path.exists() else "create"
        return evidence

    def write_text(
        self,
        raw_path: str,
        content: str,
        *,
        expected_path: str,
        expected_exists: bool,
        expected_before_sha256: str | None,
        expected_content_sha256: str,
    ) -> dict[str, object]:
        preview = self.preview_text_write(raw_path, content)
        if not bool(preview.get("allowed")):
            raise ValueError(str(preview.get("error", "WRITE_PREVIEW_REJECTED")))

        if str(preview["path"]) != expected_path:
            raise RuntimeError("WRITE_TARGET_CHANGED")
        if bool(preview["exists"]) != expected_exists:
            raise RuntimeError("WRITE_TARGET_CHANGED")
        if preview.get("before_sha256") != expected_before_sha256:
            raise RuntimeError("WRITE_TARGET_CHANGED")
        if preview.get("new_sha256") != expected_content_sha256:
            raise RuntimeError("WRITE_CONTENT_CHANGED")

        path = Path(str(preview["path"]))
        normalized = self._normalize_text(content)
        payload = normalized.encode("utf-8")

        evidence: dict[str, object] = {
            "path": str(path),
            "existed_before": expected_exists,
            "changed": bool(preview["changed"]),
            "bytes_written": len(payload),
            "sha256": expected_content_sha256,
            "atomic_replace": False,
            "write_verified": False,
        }

        if not bool(preview["changed"]) and expected_exists:
            evidence["written"] = False
            evidence["write_verified"] = True
            return evidence

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".theos.tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)

            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        written = path.read_bytes()
        written_sha256 = hashlib.sha256(written).hexdigest()
        if written_sha256 != expected_content_sha256:
            raise RuntimeError("WRITE_VERIFICATION_FAILED")

        evidence["written"] = True
        evidence["atomic_replace"] = True
        evidence["write_verified"] = True
        return evidence

    def preview_literal_text_replace(
        self,
        raw_path: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, object]:
        path = self.resolve(raw_path)
        old_sha256 = hashlib.sha256(old_text.encode("utf-8")).hexdigest()
        new_sha256 = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "old_text_sha256": old_sha256,
            "new_text_sha256": new_sha256,
            "allowed": False,
        }

        if (
            not old_text
            or not old_text.strip()
            or old_text == new_text
            or len(old_text) > MAX_LITERAL_REPLACE_TEXT_CHARS
            or len(new_text) > MAX_LITERAL_REPLACE_TEXT_CHARS
            or any(character in old_text for character in ("\0", "\r", "\n"))
            or any(character in new_text for character in ("\0", "\r", "\n"))
        ):
            evidence["error"] = "INVALID_LITERAL_REPLACEMENT"
            return evidence

        if not path.exists():
            evidence["error"] = "PATH_NOT_FOUND"
            return evidence
        if not path.is_file():
            evidence["error"] = "PATH_NOT_FILE"
            return evidence
        if self._is_link_like(path):
            evidence["error"] = "LINK_TARGET_NOT_ALLOWED"
            return evidence

        size_bytes = path.stat().st_size
        evidence["size_bytes"] = size_bytes
        if size_bytes > MAX_LITERAL_REPLACE_FILE_BYTES:
            evidence["error"] = "FILE_TOO_LARGE"
            return evidence

        raw_before = path.read_bytes()
        before_sha256 = hashlib.sha256(raw_before).hexdigest()
        evidence["before_sha256"] = before_sha256

        encoding = self._detect_text_encoding(raw_before)
        if encoding is None:
            evidence["error"] = "FILE_NOT_TEXT"
            return evidence

        try:
            before = raw_before.decode(encoding)
        except UnicodeDecodeError:
            evidence["error"] = "FILE_NOT_TEXT"
            return evidence

        match_count = before.count(old_text)
        evidence["match_count"] = match_count
        if match_count != 1:
            evidence["error"] = (
                "LITERAL_NOT_FOUND" if match_count == 0 else "LITERAL_NOT_UNIQUE"
            )
            return evidence

        after = before.replace(old_text, new_text, 1)
        write_encoding = encoding
        if encoding == "utf-8-sig" and not raw_before.startswith(b"\xef\xbb\xbf"):
            write_encoding = "utf-8"

        try:
            raw_after = after.encode(write_encoding)
        except UnicodeEncodeError:
            evidence["error"] = "REPLACEMENT_NOT_ENCODABLE"
            return evidence

        if len(raw_after) > MAX_LITERAL_REPLACE_FILE_BYTES:
            evidence["error"] = "RESULT_TOO_LARGE"
            return evidence

        after_sha256 = hashlib.sha256(raw_after).hexdigest()
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"antes/{path.name}",
                tofile=f"depois/{path.name}",
                n=3,
            )
        )
        if len(diff) > MAX_WRITE_PREVIEW_CHARS:
            diff = (
                f"--- antes/{path.name}\n"
                f"+++ depois/{path.name}\n"
                "@@ ocorrência literal única @@\n"
                f"-{old_text}\n"
                f"+{new_text}\n"
                "... contexto omitido pelo limite local; mudança exata preservada ..."
            )
            preview_truncated = True
            preview_mode = "focused_literal"
        else:
            preview_truncated = False
            preview_mode = "unified_diff"

        evidence.update(
            {
                "allowed": True,
                "encoding": encoding,
                "write_encoding": write_encoding,
                "after_bytes": len(raw_after),
                "after_sha256": after_sha256,
                "diff": diff,
                "preview_truncated": preview_truncated,
                "preview_mode": preview_mode,
            }
        )
        return evidence

    def replace_text_literal(
        self,
        raw_path: str,
        old_text: str,
        new_text: str,
        *,
        expected_path: str,
        expected_before_sha256: str,
        expected_after_sha256: str,
    ) -> dict[str, object]:
        preview = self.preview_literal_text_replace(
            raw_path,
            old_text,
            new_text,
        )

        if str(preview.get("path")) != expected_path:
            raise RuntimeError("LITERAL_REPLACE_TARGET_CHANGED")
        if preview.get("before_sha256") != expected_before_sha256:
            raise RuntimeError("LITERAL_REPLACE_TARGET_CHANGED")
        if not bool(preview.get("allowed")):
            raise ValueError(
                str(preview.get("error", "LITERAL_REPLACE_PREVIEW_REJECTED"))
            )
        if str(preview.get("after_sha256")) != expected_after_sha256:
            raise RuntimeError("LITERAL_REPLACE_CONTENT_CHANGED")

        path = Path(str(preview["path"]))
        raw_before = path.read_bytes()
        encoding = str(preview["encoding"])
        write_encoding = str(preview["write_encoding"])

        try:
            before = raw_before.decode(encoding)
            after = before.replace(old_text, new_text, 1)
            payload = after.encode(write_encoding)
        except (UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise RuntimeError("LITERAL_REPLACE_ENCODING_CHANGED") from exc

        payload_sha256 = hashlib.sha256(payload).hexdigest()
        if payload_sha256 != expected_after_sha256:
            raise RuntimeError("LITERAL_REPLACE_CONTENT_CHANGED")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".theos-literal-replace.tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)

            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        written = path.read_bytes()
        written_sha256 = hashlib.sha256(written).hexdigest()
        if written_sha256 != expected_after_sha256:
            raise RuntimeError("LITERAL_REPLACE_VERIFICATION_FAILED")

        return {
            "path": str(path),
            "match_count": 1,
            "bytes_written": len(written),
            "sha256": written_sha256,
            "atomic_replace": True,
            "write_verified": True,
            "encoding_preserved": True,
            "line_endings_outside_match_preserved": True,
        }

    def path_signature(self, raw_path: str) -> str | None:
        path = self.resolve(raw_path)
        if not path.exists():
            return None

        stat = path.stat()
        kind = "directory" if path.is_dir() else "file"
        parts = [
            kind,
            str(stat.st_dev),
            str(stat.st_ino),
            str(stat.st_size),
            str(stat.st_mtime_ns),
        ]
        if path.is_dir():
            try:
                names = sorted(child.name.casefold() for child in path.iterdir())
            except OSError:
                names = ["<listing-unavailable>"]
            names_digest = hashlib.sha256(
                "\0".join(names).encode("utf-8")
            ).hexdigest()
            parts.append(names_digest)
        return "|".join(parts)

    def is_protected_system_path(self, raw_path: str) -> bool:
        path = self.resolve(raw_path)

        if path.anchor and path == Path(path.anchor):
            return True

        protected_roots: list[Path] = []
        for key in (
            "SystemRoot",
            "ProgramFiles",
            "ProgramFiles(x86)",
            "ProgramData",
        ):
            value = os.environ.get(key)
            if not value:
                continue
            root = self.resolve(value)
            protected_roots.append(root)

        return any(path == root or root in path.parents for root in protected_roots)

    def preview_create_directory(self, raw_path: str) -> dict[str, object]:
        path = self.resolve(raw_path)
        parent = path.parent
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "parent": str(parent),
            "parent_exists": parent.exists(),
            "parent_is_directory": parent.is_dir(),
            "protected_system_path": self.is_protected_system_path(raw_path),
            "allowed": False,
        }
        if path.exists():
            evidence["error"] = "TARGET_ALREADY_EXISTS"
            return evidence
        if not parent.exists() or not parent.is_dir():
            evidence["error"] = "PARENT_NOT_DIRECTORY"
            return evidence

        evidence["allowed"] = True
        return evidence

    def create_directory(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_parent: str,
    ) -> dict[str, object]:
        preview = self.preview_create_directory(raw_path)
        if not bool(preview.get("allowed")):
            raise ValueError(str(preview.get("error", "CREATE_DIRECTORY_REJECTED")))
        if str(preview["path"]) != expected_path:
            raise RuntimeError("DIRECTORY_TARGET_CHANGED")
        if str(preview["parent"]) != expected_parent:
            raise RuntimeError("DIRECTORY_TARGET_CHANGED")
        if bool(preview["exists"]):
            raise RuntimeError("DIRECTORY_TARGET_CHANGED")

        path = Path(str(preview["path"]))
        path.mkdir()
        if not path.is_dir():
            raise RuntimeError("DIRECTORY_VERIFICATION_FAILED")

        return {
            "path": str(path),
            "created": True,
            "verified_directory": True,
        }

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction is not None and is_junction())

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def copy_manifest(self, raw_path: str) -> dict[str, object]:
        path = self.resolve(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "allowed": False,
            "max_entries": MAX_COPY_ENTRIES,
            "max_bytes": MAX_COPY_BYTES,
        }
        if not path.exists():
            evidence["error"] = "SOURCE_NOT_FOUND"
            return evidence
        if self._is_link_like(path):
            evidence["error"] = "LINK_SOURCE_NOT_ALLOWED"
            return evidence

        if path.is_file():
            size = path.stat().st_size
            if size > MAX_COPY_BYTES:
                evidence["error"] = "COPY_TOO_LARGE"
                evidence["total_bytes"] = size
                return evidence

            content_sha256 = self._file_sha256(path)
            manifest_payload = (
                f"ROOT_FILE\\0{size}\\0{content_sha256}".encode()
            )
            evidence.update(
                {
                    "allowed": True,
                    "kind": "file",
                    "files": 1,
                    "directories": 0,
                    "entries": 1,
                    "total_bytes": size,
                    "content_sha256": content_sha256,
                    "manifest_sha256": hashlib.sha256(
                        manifest_payload
                    ).hexdigest(),
                }
            )
            return evidence

        if not path.is_dir():
            evidence["error"] = "UNSUPPORTED_SOURCE_KIND"
            return evidence

        manifest_lines: list[str] = ["ROOT_DIRECTORY"]
        entries = 0
        files_count = 0
        directories_count = 0
        total_bytes = 0

        for current, directories, filenames in os.walk(path, topdown=True):
            current_path = Path(current)
            directories.sort(key=str.casefold)
            filenames.sort(key=str.casefold)

            for name in directories:
                child = current_path / name
                if self._is_link_like(child):
                    evidence["error"] = "LINK_ENTRY_NOT_ALLOWED"
                    evidence["link_path"] = str(child)
                    return evidence
                entries += 1
                directories_count += 1
                if entries > MAX_COPY_ENTRIES:
                    evidence["error"] = "COPY_TOO_MANY_ENTRIES"
                    evidence["entries"] = entries
                    return evidence
                relative = child.relative_to(path).as_posix()
                manifest_lines.append(f"D\\0{relative}")

            for name in filenames:
                child = current_path / name
                if self._is_link_like(child):
                    evidence["error"] = "LINK_ENTRY_NOT_ALLOWED"
                    evidence["link_path"] = str(child)
                    return evidence
                entries += 1
                files_count += 1
                if entries > MAX_COPY_ENTRIES:
                    evidence["error"] = "COPY_TOO_MANY_ENTRIES"
                    evidence["entries"] = entries
                    return evidence

                size = child.stat().st_size
                total_bytes += size
                if total_bytes > MAX_COPY_BYTES:
                    evidence["error"] = "COPY_TOO_LARGE"
                    evidence["total_bytes"] = total_bytes
                    return evidence

                relative = child.relative_to(path).as_posix()
                content_sha256 = self._file_sha256(child)
                manifest_lines.append(
                    f"F\\0{relative}\\0{size}\\0{content_sha256}"
                )

        manifest = "\\n".join(manifest_lines).encode("utf-8")
        evidence.update(
            {
                "allowed": True,
                "kind": "directory",
                "files": files_count,
                "directories": directories_count,
                "entries": entries,
                "total_bytes": total_bytes,
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            }
        )
        return evidence

    def preview_copy_path(
        self,
        raw_source: str,
        raw_destination: str,
    ) -> dict[str, object]:
        source = self.resolve(raw_source)
        destination = self.resolve(raw_destination)
        destination_parent = destination.parent

        manifest = self.copy_manifest(raw_source)
        evidence: dict[str, object] = {
            "source": str(source),
            "destination": str(destination),
            "destination_exists": destination.exists(),
            "destination_parent": str(destination_parent),
            "destination_parent_exists": destination_parent.exists(),
            "destination_parent_is_directory": destination_parent.is_dir(),
            "source_protected_system_path": self.is_protected_system_path(raw_source),
            "destination_protected_system_path": self.is_protected_system_path(
                raw_destination
            ),
            "allowed": False,
        }

        if not bool(manifest.get("allowed")):
            evidence["error"] = str(
                manifest.get("error", "COPY_SOURCE_REJECTED")
            )
            evidence["source_manifest"] = manifest
            return evidence
        if source == destination:
            evidence["error"] = "SOURCE_EQUALS_DESTINATION"
            return evidence
        if destination.exists():
            evidence["error"] = "DESTINATION_ALREADY_EXISTS"
            return evidence
        if not destination_parent.exists() or not destination_parent.is_dir():
            evidence["error"] = "DESTINATION_PARENT_NOT_DIRECTORY"
            return evidence
        if source.is_dir() and source in destination.parents:
            evidence["error"] = "DESTINATION_INSIDE_SOURCE"
            return evidence

        evidence.update(
            {
                "allowed": True,
                "source_kind": str(manifest["kind"]),
                "files": int(manifest["files"]),
                "directories": int(manifest["directories"]),
                "entries": int(manifest["entries"]),
                "total_bytes": int(manifest["total_bytes"]),
                "source_manifest_sha256": str(manifest["manifest_sha256"]),
            }
        )
        return evidence

    def copy_path(
        self,
        raw_source: str,
        raw_destination: str,
        *,
        expected_source: str,
        expected_destination: str,
        expected_source_manifest_sha256: str,
    ) -> dict[str, object]:
        preview = self.preview_copy_path(raw_source, raw_destination)
        if not bool(preview.get("allowed")):
            raise ValueError(str(preview.get("error", "COPY_REJECTED")))
        if str(preview["source"]) != expected_source:
            raise RuntimeError("COPY_TARGET_CHANGED")
        if str(preview["destination"]) != expected_destination:
            raise RuntimeError("COPY_TARGET_CHANGED")
        if (
            str(preview["source_manifest_sha256"])
            != expected_source_manifest_sha256
        ):
            raise RuntimeError("COPY_SOURCE_CHANGED")
        if bool(preview["destination_exists"]):
            raise RuntimeError("COPY_TARGET_CHANGED")

        source = Path(str(preview["source"]))
        destination = Path(str(preview["destination"]))
        source_kind = str(preview["source_kind"])
        temporary_path: Path | None = None

        try:
            if source_kind == "file":
                descriptor, temporary_name = tempfile.mkstemp(
                    dir=destination.parent,
                    prefix=f".{destination.name}.",
                    suffix=".theos-copy.tmp",
                )
                os.close(descriptor)
                temporary_path = Path(temporary_name)
                shutil.copy2(source, temporary_path)
            else:
                temporary_path = Path(
                    tempfile.mkdtemp(
                        dir=destination.parent,
                        prefix=f".{destination.name}.theos-copy-",
                    )
                )
                temporary_path.rmdir()
                shutil.copytree(source, temporary_path)

            source_after = self.copy_manifest(raw_source)
            copied = self.copy_manifest(str(temporary_path))
            if not bool(source_after.get("allowed")):
                raise RuntimeError("COPY_SOURCE_CHANGED")
            if (
                str(source_after.get("manifest_sha256"))
                != expected_source_manifest_sha256
            ):
                raise RuntimeError("COPY_SOURCE_CHANGED")
            if not bool(copied.get("allowed")):
                raise RuntimeError("COPY_VERIFICATION_FAILED")
            if (
                str(copied.get("manifest_sha256"))
                != expected_source_manifest_sha256
            ):
                raise RuntimeError("COPY_VERIFICATION_FAILED")
            if destination.exists():
                raise RuntimeError("COPY_TARGET_CHANGED")

            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None and temporary_path.exists():
                if temporary_path.is_dir():
                    shutil.rmtree(temporary_path, ignore_errors=True)
                else:
                    temporary_path.unlink(missing_ok=True)

        final_manifest = self.copy_manifest(str(destination))
        if (
            not bool(final_manifest.get("allowed"))
            or str(final_manifest.get("manifest_sha256"))
            != expected_source_manifest_sha256
        ):
            raise RuntimeError("COPY_VERIFICATION_FAILED")

        return {
            "source": str(source),
            "destination": str(destination),
            "kind": source_kind,
            "source_preserved": source.exists(),
            "destination_present": destination.exists(),
            "files": int(preview["files"]),
            "directories": int(preview["directories"]),
            "entries": int(preview["entries"]),
            "total_bytes": int(preview["total_bytes"]),
            "manifest_sha256": expected_source_manifest_sha256,
            "copy_verified": True,
            "destination_published_after_verification": True,
        }

    def preview_move_path(
        self,
        raw_source: str,
        raw_destination: str,
    ) -> dict[str, object]:
        source = self.resolve(raw_source)
        destination = self.resolve(raw_destination)
        destination_parent = destination.parent
        evidence: dict[str, object] = {
            "source": str(source),
            "destination": str(destination),
            "source_exists": source.exists(),
            "destination_exists": destination.exists(),
            "destination_parent": str(destination_parent),
            "destination_parent_exists": destination_parent.exists(),
            "destination_parent_is_directory": destination_parent.is_dir(),
            "source_protected_system_path": self.is_protected_system_path(raw_source),
            "destination_protected_system_path": self.is_protected_system_path(
                raw_destination
            ),
            "allowed": False,
        }

        if not source.exists():
            evidence["error"] = "SOURCE_NOT_FOUND"
            return evidence
        if bool(evidence["source_protected_system_path"]):
            evidence["error"] = "PROTECTED_SYSTEM_SOURCE"
            return evidence
        if source == destination:
            evidence["error"] = "SOURCE_EQUALS_DESTINATION"
            return evidence
        if destination.exists():
            evidence["error"] = "DESTINATION_ALREADY_EXISTS"
            return evidence
        if not destination_parent.exists() or not destination_parent.is_dir():
            evidence["error"] = "DESTINATION_PARENT_NOT_DIRECTORY"
            return evidence
        if source.is_dir() and source in destination.parents:
            evidence["error"] = "DESTINATION_INSIDE_SOURCE"
            return evidence

        evidence["source_kind"] = "directory" if source.is_dir() else "file"
        evidence["source_signature"] = self.path_signature(raw_source)
        evidence["allowed"] = True
        return evidence

    def move_path(
        self,
        raw_source: str,
        raw_destination: str,
        *,
        expected_source: str,
        expected_destination: str,
        expected_source_signature: str,
    ) -> dict[str, object]:
        preview = self.preview_move_path(raw_source, raw_destination)
        if not bool(preview.get("allowed")):
            raise ValueError(str(preview.get("error", "MOVE_REJECTED")))
        if str(preview["source"]) != expected_source:
            raise RuntimeError("MOVE_TARGET_CHANGED")
        if str(preview["destination"]) != expected_destination:
            raise RuntimeError("MOVE_TARGET_CHANGED")
        if preview.get("source_signature") != expected_source_signature:
            raise RuntimeError("MOVE_SOURCE_CHANGED")
        if bool(preview["destination_exists"]):
            raise RuntimeError("MOVE_TARGET_CHANGED")

        source = Path(str(preview["source"]))
        destination = Path(str(preview["destination"]))
        kind = str(preview["source_kind"])

        shutil.move(str(source), str(destination))

        if source.exists() or not destination.exists():
            raise RuntimeError("MOVE_VERIFICATION_FAILED")

        return {
            "source": str(source),
            "destination": str(destination),
            "kind": kind,
            "source_absent_after_move": True,
            "destination_present_after_move": True,
        }

    def preview_trash_path(self, raw_path: str) -> dict[str, object]:
        path = self.resolve(raw_path)
        protected = self.is_protected_system_path(raw_path)
        evidence: dict[str, object] = {
            "path": str(path),
            "exists": path.exists(),
            "protected_system_path": protected,
            "allowed": False,
        }
        if not path.exists():
            evidence["error"] = "PATH_NOT_FOUND"
            return evidence
        if protected:
            evidence["error"] = "PROTECTED_SYSTEM_PATH"
            return evidence

        evidence["kind"] = "directory" if path.is_dir() else "file"
        evidence["source_signature"] = self.path_signature(raw_path)
        if path.is_file():
            evidence["size_bytes"] = path.stat().st_size
        evidence["allowed"] = True
        return evidence

    def trash_path(
        self,
        raw_path: str,
        *,
        expected_path: str,
        expected_source_signature: str,
    ) -> dict[str, object]:
        preview = self.preview_trash_path(raw_path)
        if not bool(preview.get("allowed")):
            raise ValueError(str(preview.get("error", "TRASH_REJECTED")))
        if str(preview["path"]) != expected_path:
            raise RuntimeError("TRASH_TARGET_CHANGED")
        if preview.get("source_signature") != expected_source_signature:
            raise RuntimeError("TRASH_SOURCE_CHANGED")

        path = Path(str(preview["path"]))
        result_code, aborted = _recycle_with_shell(path)
        if result_code != 0 or aborted:
            raise RuntimeError(
                f"RECYCLE_BIN_OPERATION_FAILED:{result_code}:aborted={aborted}"
            )
        if path.exists():
            raise RuntimeError("TRASH_VERIFICATION_FAILED")

        return {
            "path": str(path),
            "kind": str(preview["kind"]),
            "sent_to_recycle_bin": True,
            "path_absent_after_operation": True,
        }

    @staticmethod
    def _normalize_text(content: str) -> str:
        return content.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _detect_text_encoding(raw: bytes) -> str | None:
        if not raw:
            return "utf-8"

        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return "utf-16"

        if b"\x00" in raw:
            return None

        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                raw.decode("cp1252")
            except UnicodeDecodeError:
                return None
            return "cp1252"
        return "utf-8-sig"
