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
