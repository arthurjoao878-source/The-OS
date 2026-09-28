from __future__ import annotations

from theos.core.window_targets import (
    is_window_target_token,
    normalize_window_query,
    window_target_matches_query,
)
from theos.integrations.windows.desktop_windows import _window_target_token


def test_window_target_token_is_opaque_stable_and_handle_specific() -> None:
    first = _window_target_token(101, 4321, "Calculadora")
    same = _window_target_token(101, 4321, "Calculadora")
    other_handle = _window_target_token(202, 4321, "Calculadora")

    assert is_window_target_token(first) is True
    assert first == same
    assert first != other_handle
    assert is_window_target_token(first.upper()) is False
    assert is_window_target_token("a" * 63) is False


def test_window_query_is_bounded_and_matches_title_or_process_name() -> None:
    assert normalize_window_query(" Bloco de Notas ") == "Bloco de Notas"
    assert normalize_window_query("") is None
    assert normalize_window_query("x" * 81) is None
    assert normalize_window_query("linha\nquebrada") is None

    assert window_target_matches_query(
        "bloco DE notas",
        "Sem título - Bloco de Notas",
        "Notepad.exe",
    )
    assert window_target_matches_query(
        "NOTEPAD",
        "Documento",
        "notepad.exe",
    )
    assert not window_target_matches_query(
        "Calculadora",
        "Sem título - Bloco de Notas",
        "Notepad.exe",
    )
