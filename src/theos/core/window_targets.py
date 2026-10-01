from __future__ import annotations

WINDOW_TARGET_TOKEN_CHARS = 64
MAX_WINDOW_QUERY_CHARS = 80


def is_window_target_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == WINDOW_TARGET_TOKEN_CHARS
        and all(character in "0123456789abcdef" for character in value)
    )


def normalize_window_query(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized or len(normalized) > MAX_WINDOW_QUERY_CHARS:
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        return None
    if any(0xD800 <= ord(character) <= 0xDFFF for character in normalized):
        return None
    return normalized


def window_target_matches_query(
    query: str,
    bounded_title: str,
    process_name: str,
) -> bool:
    normalized = normalize_window_query(query)
    if normalized is None:
        return False

    needle = normalized.casefold()
    return (
        needle in bounded_title.casefold()
        or needle in process_name.casefold()
    )

MIN_WINDOW_MULTI_QUERIES = 2
MAX_WINDOW_MULTI_QUERIES = 4


def normalize_window_queries(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if not MIN_WINDOW_MULTI_QUERIES <= len(value) <= MAX_WINDOW_MULTI_QUERIES:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        query = normalize_window_query(item)
        if query is None:
            return None
        folded = query.casefold()
        if folded in seen:
            return None
        seen.add(folded)
        normalized.append(query)

    return tuple(normalized)
