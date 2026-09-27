from __future__ import annotations

import pytest

from theos.core.tools import ToolCall, ToolValidationError, build_default_tool_catalog


def test_tool_catalog_builds_allowlisted_action_request() -> None:
    catalog = build_default_tool_catalog()

    request = catalog.build_action_request(
        ToolCall(
            name="open_application",
            arguments={"application": "  Bloco de Notas  "},
        )
    )

    assert request.action == "open_application"
    assert request.arguments == {"application": "Bloco de Notas"}


def test_tool_catalog_builds_file_system_requests() -> None:
    catalog = build_default_tool_catalog()

    inspect_request = catalog.build_action_request(
        ToolCall(
            name="inspect_path",
            arguments={"path": r"  C:\Projetos\TheOS  "},
        )
    )
    find_request = catalog.build_action_request(
        ToolCall(
            name="find_path",
            arguments={
                "root": r" C:\Projetos\TheOS ",
                "query": " README ",
            },
        )
    )
    open_request = catalog.build_action_request(
        ToolCall(
            name="open_path",
            arguments={"path": r" C:\Projetos\TheOS "},
        )
    )
    read_request = catalog.build_action_request(
        ToolCall(
            name="read_text_file",
            arguments={"path": r" C:\Projetos\TheOS\README.md "},
        )
    )

    assert inspect_request.arguments == {"path": r"C:\Projetos\TheOS"}
    assert find_request.arguments == {
        "root": r"C:\Projetos\TheOS",
        "query": "README",
    }
    assert open_request.arguments == {"path": r"C:\Projetos\TheOS"}
    assert read_request.arguments == {"path": r"C:\Projetos\TheOS\README.md"}


def test_tool_catalog_rejects_unknown_tool() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="run_arbitrary_command",
                arguments={"command": "whoami"},
            )
        )


def test_tool_catalog_rejects_extra_arguments() -> None:
    catalog = build_default_tool_catalog()

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="open_application",
                arguments={
                    "application": "Notepad",
                    "unexpected": "value",
                },
            )
        )

    with pytest.raises(ToolValidationError):
        catalog.build_action_request(
            ToolCall(
                name="inspect_path",
                arguments={
                    "path": r"C:\Temp",
                    "recursive": True,
                },
            )
        )
