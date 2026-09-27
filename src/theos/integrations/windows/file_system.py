from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

MAX_DIRECTORY_ENTRIES = 30
MAX_FIND_RESULTS = 20
MAX_FIND_DEPTH = 4
MAX_READ_BYTES = 16 * 1024
MAX_WRITE_BYTES = 16 * 1024
MAX_WRITE_PREVIEW_CHARS = 3500


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
