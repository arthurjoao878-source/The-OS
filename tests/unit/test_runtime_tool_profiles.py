from __future__ import annotations

from theos.bootstrap import build_action_registry, build_tool_catalog
from theos.core.tools import (
    DEVELOPMENT_TOOL_NAMES,
    build_assistant_tool_catalog,
    build_default_tool_catalog,
    build_development_tool_catalog,
)

EXPECTED_DEVELOPMENT = frozenset(
    {
        "check_python_syntax",
        "check_python_static",
        "check_python_static_many",
        "run_python_unit_test_file",
        "run_python_unit_test_files",
        "git_commit_staged_new_file",
        "git_commit_staged_file",
        "git_diff_file",
        "git_stage_file",
        "git_stage_new_file",
        "git_unstage_new_file",
        "git_unstage_file",
        "git_fetch_remote_main",
        "git_remote_head_snapshot",
        "git_remote_identity_snapshot",
        "git_status_snapshot",
    }
)

EXPECTED_ASSISTANT = frozenset(
    {
        "open_application",
        "inspect_path",
        "find_path",
        "search_text",
        "open_path",
        "read_text_file",
        "read_text_lines",
        "create_directory",
        "copy_path",
        "move_path",
        "trash_path",
        "system_status",
        "process_snapshot",
        "terminate_process",
        "window_snapshot",
        "window_snapshot_many",
        "semantic_window_snapshot",
        "invoke_semantic_button",
        "activate_window",
        "press_key",
        "press_shortcut",
        "click_window",
        "move_cursor_window_anchor",
        "click_window_anchor",
        "double_click_window",
        "double_click_window_anchor",
        "drag_window_anchor",
        "scroll_window_anchor",
        "scroll_window",
        "type_text",
        "place_window",
        "place_window_pair",
        "place_window_set",
        "restore_window",
        "maximize_window",
        "minimize_window",
        "close_window",
        "replace_text_literal",
        "replace_text_block",
        "write_text_file",
    }
)


def _names(catalog) -> frozenset[str]:
    return frozenset(item.name for item in catalog.definitions())


def test_m94r_profiles_partition_existing_catalog_without_loss() -> None:
    full = _names(build_default_tool_catalog())
    assistant = _names(build_assistant_tool_catalog())
    development = _names(build_development_tool_catalog())

    assert len(full) == 56
    assert len(assistant) == 40
    assert len(development) == 16
    assert assistant.isdisjoint(development)
    assert assistant | development == full


def test_m94r_development_profile_is_exactly_classified_tooling() -> None:
    assert DEVELOPMENT_TOOL_NAMES == EXPECTED_DEVELOPMENT
    assert _names(build_development_tool_catalog()) == EXPECTED_DEVELOPMENT


def test_m94r_assistant_profile_preserves_exact_existing_user_capabilities() -> None:
    assert _names(build_assistant_tool_catalog()) == EXPECTED_ASSISTANT


def test_m94r_normal_runtime_uses_assistant_profile() -> None:
    runtime = _names(build_tool_catalog())

    assert runtime == EXPECTED_ASSISTANT
    assert runtime.isdisjoint(EXPECTED_DEVELOPMENT)


def test_m94r_development_actions_remain_implemented_in_host_registry() -> None:
    registry_names = frozenset(build_action_registry().names())

    assert EXPECTED_DEVELOPMENT <= registry_names
    assert EXPECTED_ASSISTANT <= registry_names
    assert len(registry_names) == 56


def test_m94r_full_catalog_remains_available_for_development_and_tests() -> None:
    full = _names(build_default_tool_catalog())

    assert EXPECTED_DEVELOPMENT <= full
    assert EXPECTED_ASSISTANT <= full
    assert len(full) == 56
