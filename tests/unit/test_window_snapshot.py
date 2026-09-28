from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import WindowSnapshotAction


class _FakeWindowAdapter:
    def __init__(self) -> None:
        self.snapshot_calls = 0

    def snapshot(self) -> dict[str, object]:
        self.snapshot_calls += 1
        return {
            "observed_windows": 3,
            "returned_windows": 3,
            "max_results": 12,
            "max_title_chars": 160,
            "order": "windows_z_order",
            "fields": ["title", "pid", "process_name", "target_token"],
            "windows": [
                {
                    "title": "Documento - Bloco de Notas",
                    "pid": 100,
                    "process_name": "notepad.exe",
                    "target_token": "1" * 64,
                },
                {
                    "title": "ChatGPT",
                    "pid": 200,
                    "process_name": "ChatGPT.exe",
                    "target_token": "2" * 64,
                },
                {
                    "title": "THE OS — LYRA",
                    "pid": 300,
                    "process_name": "python.exe",
                    "target_token": "3" * 64,
                },
            ],
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
    assert "capturas de tela" in preview.text
    assert adapter.snapshot_calls == 0


def test_window_snapshot_returns_bounded_evidence() -> None:
    adapter = _FakeWindowAdapter()
    action = WindowSnapshotAction(adapter)
    request = ActionRequest(action="window_snapshot", arguments={})

    result = action.execute(request)

    assert result.success is True
    assert adapter.snapshot_calls == 1
    assert result.evidence["returned_windows"] == 3
    assert result.evidence["max_results"] == 12
    assert result.evidence["fields"] == [
        "title",
        "pid",
        "process_name",
        "target_token",
    ]
