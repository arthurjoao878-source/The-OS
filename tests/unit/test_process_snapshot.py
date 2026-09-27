from __future__ import annotations

from types import SimpleNamespace

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.processes import ProcessSnapshotAction
from theos.integrations.windows import processes as processes_module
from theos.integrations.windows.processes import (
    MAX_PROCESS_RESULTS,
    WindowsProcessAdapter,
)


class _FakeProcess:
    def __init__(self, pid: int, name: str, rss: int) -> None:
        self.info = {
            "pid": pid,
            "name": name,
            "memory_info": SimpleNamespace(rss=rss),
        }


def test_process_snapshot_is_bounded_and_sorted(monkeypatch) -> None:
    fake = [
        _FakeProcess(pid=index, name=f"proc-{index}", rss=index * 100)
        for index in range(1, 20)
    ]
    monkeypatch.setattr(
        processes_module.psutil,
        "process_iter",
        lambda *, attrs, ad_value: fake
        if attrs == ["pid", "name", "memory_info"] and ad_value is None
        else [],
    )

    snapshot = WindowsProcessAdapter().snapshot()

    assert snapshot["observed_processes"] == 19
    assert snapshot["returned_processes"] == MAX_PROCESS_RESULTS
    assert snapshot["max_results"] == MAX_PROCESS_RESULTS
    assert len(snapshot["processes"]) == MAX_PROCESS_RESULTS
    assert snapshot["processes"][0] == {
        "pid": 19,
        "name": "proc-19",
        "rss_bytes": 1900,
    }
    assert set(snapshot["processes"][0]) == {"pid", "name", "rss_bytes"}


class _CountingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def snapshot(self) -> dict[str, object]:
        self.calls += 1
        return {
            "observed_processes": 2,
            "returned_processes": 2,
            "max_results": 12,
            "sort": "rss_bytes_desc",
            "fields": ["pid", "name", "rss_bytes"],
            "processes": [
                {"pid": 10, "name": "A.exe", "rss_bytes": 200},
                {"pid": 20, "name": "B.exe", "rss_bytes": 100},
            ],
        }


def test_process_preview_does_not_enumerate_and_action_is_confirm() -> None:
    adapter = _CountingAdapter()
    action = ProcessSnapshotAction(adapter)
    request = ActionRequest(action="process_snapshot", arguments={})

    preview = action.confirmation_preview(request)

    assert action.risk is ActionRisk.CONFIRM
    assert preview.allowed is True
    assert "12 processos" in preview.text
    assert adapter.calls == 0

    result = action.execute(request)

    assert result.success is True
    assert adapter.calls == 1
    assert result.evidence["returned_processes"] == 2
