from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

MAX_DIRECTORY_ENTRIES = 30
MAX_FIND_RESULTS = 20
MAX_FIND_DEPTH = 4
MAX_READ_BYTES = 16 * 1024


class WindowsFileSystemAdapter:
    """Bounded Windows filesystem inspection, search, open, and text-read primitives."""

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
