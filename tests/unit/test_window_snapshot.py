from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import WindowSnapshotAction
from theos.core.window_observations import (
    WINDOW_OBSERVATION_HANDLE_VERSION,
    WINDOW_OBSERVATION_TTL_SECONDS,
    build_window_observation_handle,
)


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.snapshot_calls = 0
        self.snapshot_queries: list[str | None] = []

    def snapshot(self, query: str | None = None) -> dict[str, object]:
        self.snapshot_calls += 1
        self.snapshot_queries.append(query)
        filtered = query is not None
        rows = [
            {
                "title": "Documento - Bloco de Notas",
                "pid": 100,
                "process_name": "notepad.exe",
                "target_token": "1" * 64,
                "observation_handle": build_window_observation_handle("1" * 64),
            },
            {
                "title": "ChatGPT",
                "pid": 200,
                "process_name": "ChatGPT.exe",
                "target_token": "2" * 64,
                "observation_handle": build_window_observation_handle("2" * 64),
            },
            {
                "title": "THE OS — LYRA",
                "pid": 300,
                "process_name": "python.exe",
                "target_token": "3" * 64,
                "observation_handle": build_window_observation_handle("3" * 64),
            },
        ]
        selected = [rows[0]] if filtered else rows
        return {
            "observed_windows": 18 if filtered else 3,
            "matched_windows": len(selected),
            "returned_windows": len(selected),
            "max_results": 12,
            "max_title_chars": 160,
            "filter_applied": filtered,
            "filter_query": query,
            "filter_match": "casefold_substring_title_or_process_name",
            "order": (
                "windows_z_order_within_filter"
                if filtered
                else "windows_z_order"
            ),
            "fields": [
                "title",
                "pid",
                "process_name",
                "target_token",
                "observation_handle",
            ],
            "observation_handle_version": WINDOW_OBSERVATION_HANDLE_VERSION,
            "observation_handle_ttl_seconds": WINDOW_OBSERVATION_TTL_SECONDS,
            "windows": selected,
        }


def test_window_snapshot_preview_is_static_and_privacy_gated() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotAction(adapter)
    request = ActionRequest(action="window_snapshot", arguments={})

    assert action.risk is ActionRisk.CONFIRM

    preview = action.confirmation_preview(request)

    assert preview.allowed is True
    assert "INSPECIONAR JANELAS VISÍVEIS" in preview.text
    assert "12 janelas" in preview.text
    assert "Sem filtro local" in preview.text
    assert "capturas de tela" in preview.text
    assert adapter.snapshot_calls == 0


def test_window_snapshot_returns_bounded_evidence() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotAction(adapter)
    request = ActionRequest(action="window_snapshot", arguments={})

    result = action.execute(request)

    assert result.success is True
    assert adapter.snapshot_calls == 1
    assert adapter.snapshot_queries == [None]
    assert result.evidence["returned_windows"] == 3
    assert result.evidence["max_results"] == 12
    assert result.evidence["filter_applied"] is False
    assert result.evidence["fields"] == [
        "title",
        "pid",
        "process_name",
        "target_token",
        "observation_handle",
    ]
    assert result.evidence["observation_handle_version"] == 1
    assert result.evidence["observation_handle_ttl_seconds"] == 120
    assert "observation_handle" in result.evidence["windows"][0]


def test_window_snapshot_forwards_local_filter_before_output_cap() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotAction(adapter)
    request = ActionRequest(
        action="window_snapshot",
        arguments={"query": " Bloco de Notas "},
    )

    preview = action.confirmation_preview(request)
    assert preview.allowed is True
    assert "Filtro local solicitado: Bloco de Notas" in preview.text
    assert adapter.snapshot_calls == 0

    result = action.execute(request)

    assert result.success is True
    assert adapter.snapshot_queries == ["Bloco de Notas"]
    assert result.evidence["observed_windows"] == 18
    assert result.evidence["matched_windows"] == 1
    assert result.evidence["returned_windows"] == 1
    assert result.evidence["filter_applied"] is True
    assert result.evidence["filter_query"] == "Bloco de Notas"
    assert "1 corresponderam ao filtro local" in result.message
