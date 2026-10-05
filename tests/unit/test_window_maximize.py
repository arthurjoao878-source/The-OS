from __future__ import annotations

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.desktop_windows import MaximizeWindowAction
from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog
from theos.core.window_observations import build_window_observation_handle


class _FakeWindowAdapter:
    def __init__(self, *, already_maximized: bool = False) -> None:
        self.calls: list[tuple[int, str, str]] = []
        self.already_maximized = already_maximized

    def maximize_window(
        self,
        pid: int,
        title: str,
        target_token: str,
    ) -> dict[str, object]:
        self.calls.append((pid, title, target_token))
        return {
            "pid": pid,
            "title": title,
            "process_name": "CalculatorApp.exe",
            "target_token": target_token,
            "maximized": True,
            "maximized_verified": True,
            "already_maximized": self.already_maximized,
            "title_match": "pid_bounded_title_and_opaque_token_exact",
        }


def test_maximize_window_uses_exact_known_target() -> None:
    adapter = _FakeWindowAdapter()
    action = MaximizeWindowAction(adapter)
    request = ActionRequest(
        action="maximize_window",
        arguments={
            "pid": 4321,
            "title": "Calculadora",
            "target_token": "a" * 64,
        },
    )

    assert action.risk is ActionRisk.NORMAL

    result = action.execute(request)

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert adapter.calls == [(4321, "Calculadora", "a" * 64)]
    assert result.evidence["target_token"] == "a" * 64
    assert result.evidence["maximized_verified"] is True
    assert result.evidence["title_match"] == (
        "pid_bounded_title_and_opaque_token_exact"
    )
    assert "PID 4321" in result.message



def test_maximize_window_can_verify_postcondition_without_new_dispatch() -> None:
    adapter = _FakeWindowAdapter(already_maximized=True)
    action = MaximizeWindowAction(adapter)
    request = ActionRequest(
        action="maximize_window",
        arguments={
            "pid": 4321,
            "title": "Calculadora",
            "target_token": "e" * 64,
        },
    )

    result = action.execute(request)

    assert result.success is True
    assert result.effect_dispatched is False
    assert result.postcondition_verified is True
    assert result.evidence["already_maximized"] is True


def test_maximize_window_validates_fresh_observation_handle() -> None:
    adapter = _FakeWindowAdapter()
    action = MaximizeWindowAction(adapter)
    token = "f" * 64
    handle = build_window_observation_handle(token)
    request = ActionRequest(
        action="maximize_window",
        arguments={
            "pid": 4321,
            "title": "Calculadora",
            "target_token": token,
            "observation_handle": handle,
        },
    )

    result = action.execute(request)

    assert result.success is True
    assert result.effect_dispatched is True
    assert result.postcondition_verified is True
    assert result.evidence["observation_handle_validated"] is True
    assert result.evidence["observation_id"] == handle["observation_id"]
    assert "Referência de observação temporária validada." in result.message


def test_maximize_window_rejects_expired_observation_before_dispatch() -> None:
    adapter = _FakeWindowAdapter()
    action = MaximizeWindowAction(adapter)
    token = "9" * 64
    handle = build_window_observation_handle(
        token,
        now=1,
        observation_id="8" * 32,
    )
    request = ActionRequest(
        action="maximize_window",
        arguments={
            "pid": 4321,
            "title": "Calculadora",
            "target_token": token,
            "observation_handle": handle,
        },
    )

    result = action.execute(request)

    assert result.success is False
    assert result.effect_dispatched is False
    assert result.postcondition_verified is None
    assert result.error_code == "WINDOW_OBSERVATION_EXPIRED"
    assert adapter.calls == []


def test_catalog_builds_maximize_window_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="maximize_window",
            arguments={
                "pid": 4321,
                "title": " Calculadora ",
                "target_token": "b" * 64,
            },
        )
    )

    assert request.action == "maximize_window"
    assert request.arguments == {
        "pid": 4321,
        "title": "Calculadora",
        "target_token": "b" * 64,
    }


def test_catalog_rejects_invalid_maximize_window_target() -> None:
    catalog = build_default_tool_catalog()

    for arguments in (
        {
            "pid": 0,
            "title": "Calculadora",
            "target_token": "c" * 64,
        },
        {
            "pid": 4321,
            "title": "Calculadora",
            "target_token": "BAD",
        },
    ):
        try:
            catalog.build_action_request(
                ToolCall(
                    name="maximize_window",
                    arguments=arguments,
                )
            )
        except ToolValidationError:
            pass
        else:
            raise AssertionError("invalid maximize-window target must be rejected")
