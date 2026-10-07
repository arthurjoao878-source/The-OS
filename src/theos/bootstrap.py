from __future__ import annotations

from pathlib import Path

from theos.core.actions.desktop_windows import (
    ActivateWindowAction,
    ClickWindowAction,
    ClickWindowAnchorAction,
    CloseWindowAction,
    DoubleClickWindowAction,
    DoubleClickWindowAnchorAction,
    DragWindowAnchorAction,
    InvokeSemanticButtonAction,
    MaximizeWindowAction,
    MinimizeWindowAction,
    MoveCursorWindowAnchorAction,
    PlaceWindowAction,
    PlaceWindowPairAction,
    PlaceWindowSetAction,
    PressKeyAction,
    PressShortcutAction,
    RestoreWindowAction,
    ScrollWindowAction,
    ScrollWindowAnchorAction,
    SelectSemanticRadioButtonAction,
    SemanticWindowSnapshotAction,
    SetSemanticCheckboxStateAction,
    SetSemanticComboBoxIndexAction,
    SetSemanticListBoxIndexAction,
    SetSemanticTextAction,
    TypeTextAction,
    WindowSnapshotAction,
    WindowSnapshotManyAction,
)
from theos.core.actions.file_system import (
    CheckPythonStaticAction,
    CheckPythonStaticManyAction,
    CheckPythonSyntaxAction,
    CopyPathAction,
    CreateDirectoryAction,
    FindPathAction,
    InspectPathAction,
    MovePathAction,
    OpenPathAction,
    ReadTextFileAction,
    ReadTextLinesAction,
    ReplaceTextBlockAction,
    ReplaceTextLiteralAction,
    SearchTextAction,
    TrashPathAction,
    WriteTextFileAction,
)
from theos.core.actions.git_local import (
    GitCommitStagedFileAction,
    GitCommitStagedNewFileAction,
    GitDiffFileAction,
    GitFetchRemoteMainAction,
    GitRemoteHeadSnapshotAction,
    GitRemoteIdentitySnapshotAction,
    GitStageFileAction,
    GitStageNewFileAction,
    GitStatusSnapshotAction,
    GitUnstageFileAction,
    GitUnstageNewFileAction,
)
from theos.core.actions.open_application import OpenApplicationAction
from theos.core.actions.processes import ProcessSnapshotAction, TerminateProcessAction
from theos.core.actions.python_tests import (
    RunPythonUnitTestFileAction,
    RunPythonUnitTestFilesAction,
)
from theos.core.actions.registry import ActionRegistry
from theos.core.actions.system_status import SystemStatusAction
from theos.core.applications.registry import ApplicationRegistry
from theos.core.tools import ToolCatalog, build_assistant_tool_catalog
from theos.integrations.ai import AIProvider
from theos.integrations.ai import build_ai_provider as create_ai_provider
from theos.integrations.windows.applications import WindowsApplicationAdapter
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.integrations.windows.git_local import WindowsLocalGitAdapter
from theos.integrations.windows.processes import WindowsProcessAdapter
from theos.integrations.windows.python_tests import WindowsPythonUnitTestAdapter
from theos.integrations.windows.system_status import WindowsSystemStatusAdapter
from theos.lyra.memory.service import MemoryService
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


def build_action_registry() -> ActionRegistry:
    applications = ApplicationRegistry()
    windows_applications = WindowsApplicationAdapter()
    windows_desktop = WindowsDesktopWindowAdapter()
    windows_files = WindowsFileSystemAdapter()
    windows_processes = WindowsProcessAdapter()
    repository_root = Path(__file__).resolve().parents[2]
    python_tests = WindowsPythonUnitTestAdapter(repository_root)
    local_git = WindowsLocalGitAdapter(repository_root)
    windows_system = WindowsSystemStatusAdapter()

    open_application = OpenApplicationAction(applications, windows_applications)
    inspect_path = InspectPathAction(windows_files)
    check_python_syntax = CheckPythonSyntaxAction(windows_files)
    check_python_static = CheckPythonStaticAction(windows_files)
    check_python_static_many = CheckPythonStaticManyAction(windows_files)
    run_python_unit_test_file = RunPythonUnitTestFileAction(python_tests)
    run_python_unit_test_files = RunPythonUnitTestFilesAction(python_tests)
    git_status_snapshot = GitStatusSnapshotAction(local_git)
    git_remote_identity_snapshot = GitRemoteIdentitySnapshotAction(local_git)
    git_remote_head_snapshot = GitRemoteHeadSnapshotAction(local_git)
    git_fetch_remote_main = GitFetchRemoteMainAction(local_git)
    git_commit_staged_file = GitCommitStagedFileAction(local_git)
    git_commit_staged_new_file = GitCommitStagedNewFileAction(local_git)
    git_diff_file = GitDiffFileAction(local_git)
    git_stage_file = GitStageFileAction(local_git)
    git_stage_new_file = GitStageNewFileAction(local_git)
    git_unstage_file = GitUnstageFileAction(local_git)
    git_unstage_new_file = GitUnstageNewFileAction(local_git)
    find_path = FindPathAction(windows_files)
    open_path = OpenPathAction(windows_files)
    read_text_file = ReadTextFileAction(windows_files)
    read_text_lines = ReadTextLinesAction(windows_files)
    replace_text_literal = ReplaceTextLiteralAction(windows_files)
    replace_text_block = ReplaceTextBlockAction(windows_files)
    search_text = SearchTextAction(windows_files)
    write_text_file = WriteTextFileAction(windows_files)
    create_directory = CreateDirectoryAction(windows_files)
    copy_path = CopyPathAction(windows_files)
    move_path = MovePathAction(windows_files)
    trash_path = TrashPathAction(windows_files)
    process_snapshot = ProcessSnapshotAction(windows_processes)
    terminate_process = TerminateProcessAction(windows_processes)
    window_snapshot = WindowSnapshotAction(windows_desktop)
    window_snapshot_many = WindowSnapshotManyAction(windows_desktop)
    semantic_window_snapshot = SemanticWindowSnapshotAction(windows_desktop)
    invoke_semantic_button = InvokeSemanticButtonAction(windows_desktop)
    select_semantic_radio_button = SelectSemanticRadioButtonAction(windows_desktop)
    set_semantic_checkbox_state = SetSemanticCheckboxStateAction(windows_desktop)
    set_semantic_combo_box_index = SetSemanticComboBoxIndexAction(windows_desktop)
    set_semantic_list_box_index = SetSemanticListBoxIndexAction(windows_desktop)
    set_semantic_text = SetSemanticTextAction(windows_desktop)
    activate_window = ActivateWindowAction(windows_desktop)
    move_cursor_window_anchor = MoveCursorWindowAnchorAction(windows_desktop)
    click_window = ClickWindowAction(windows_desktop)
    click_window_anchor = ClickWindowAnchorAction(windows_desktop)
    double_click_window = DoubleClickWindowAction(windows_desktop)
    double_click_window_anchor = DoubleClickWindowAnchorAction(windows_desktop)
    drag_window_anchor = DragWindowAnchorAction(windows_desktop)
    scroll_window_anchor = ScrollWindowAnchorAction(windows_desktop)
    scroll_window = ScrollWindowAction(windows_desktop)
    press_key = PressKeyAction(windows_desktop)
    press_shortcut = PressShortcutAction(windows_desktop)
    type_text = TypeTextAction(windows_desktop)
    place_window = PlaceWindowAction(windows_desktop)
    place_window_pair = PlaceWindowPairAction(windows_desktop)
    place_window_set = PlaceWindowSetAction(windows_desktop)
    restore_window = RestoreWindowAction(windows_desktop)
    maximize_window = MaximizeWindowAction(windows_desktop)
    minimize_window = MinimizeWindowAction(windows_desktop)
    close_window = CloseWindowAction(windows_desktop)
    system_status = SystemStatusAction(windows_system)

    registry = ActionRegistry()
    registry.register(
        open_application.name,
        open_application.execute,
        risk=open_application.risk_for,
    )
    registry.register(
        inspect_path.name,
        inspect_path.execute,
        risk=inspect_path.risk,
    )
    registry.register(
        check_python_syntax.name,
        check_python_syntax.execute,
        risk=check_python_syntax.risk,
        confirmation_preview=check_python_syntax.confirmation_preview,
    )
    registry.register(
        check_python_static.name,
        check_python_static.execute,
        risk=check_python_static.risk,
        confirmation_preview=check_python_static.confirmation_preview,
    )
    registry.register(
        check_python_static_many.name,
        check_python_static_many.execute,
        risk=check_python_static_many.risk,
        confirmation_preview=check_python_static_many.confirmation_preview,
    )
    registry.register(
        run_python_unit_test_file.name,
        run_python_unit_test_file.execute,
        risk=run_python_unit_test_file.risk,
        confirmation_preview=run_python_unit_test_file.confirmation_preview,
    )
    registry.register(
        run_python_unit_test_files.name,
        run_python_unit_test_files.execute,
        risk=run_python_unit_test_files.risk,
        confirmation_preview=run_python_unit_test_files.confirmation_preview,
    )
    registry.register(
        git_fetch_remote_main.name,
        git_fetch_remote_main.execute,
        risk=git_fetch_remote_main.risk,
        confirmation_preview=git_fetch_remote_main.confirmation_preview,
    )
    registry.register(
        git_remote_head_snapshot.name,
        git_remote_head_snapshot.execute,
        risk=git_remote_head_snapshot.risk,
        confirmation_preview=git_remote_head_snapshot.confirmation_preview,
    )
    registry.register(
        git_remote_identity_snapshot.name,
        git_remote_identity_snapshot.execute,
        risk=git_remote_identity_snapshot.risk,
        confirmation_preview=git_remote_identity_snapshot.confirmation_preview,
    )
    registry.register(
        git_status_snapshot.name,
        git_status_snapshot.execute,
        risk=git_status_snapshot.risk,
        confirmation_preview=git_status_snapshot.confirmation_preview,
    )
    registry.register(
        git_commit_staged_new_file.name,
        git_commit_staged_new_file.execute,
        risk=git_commit_staged_new_file.risk,
        confirmation_preview=git_commit_staged_new_file.confirmation_preview,
    )
    registry.register(
        git_commit_staged_file.name,
        git_commit_staged_file.execute,
        risk=git_commit_staged_file.risk,
        confirmation_preview=git_commit_staged_file.confirmation_preview,
    )
    registry.register(
        git_diff_file.name,
        git_diff_file.execute,
        risk=git_diff_file.risk_for,
        confirmation_preview=git_diff_file.confirmation_preview,
    )
    registry.register(
        git_stage_file.name,
        git_stage_file.execute,
        risk=git_stage_file.risk_for,
        confirmation_preview=git_stage_file.confirmation_preview,
    )
    registry.register(
        git_stage_new_file.name,
        git_stage_new_file.execute,
        risk=git_stage_new_file.risk_for,
        confirmation_preview=git_stage_new_file.confirmation_preview,
    )
    registry.register(
        git_unstage_new_file.name,
        git_unstage_new_file.execute,
        risk=git_unstage_new_file.risk_for,
        confirmation_preview=git_unstage_new_file.confirmation_preview,
    )
    registry.register(
        git_unstage_file.name,
        git_unstage_file.execute,
        risk=git_unstage_file.risk_for,
        confirmation_preview=git_unstage_file.confirmation_preview,
    )
    registry.register(
        find_path.name,
        find_path.execute,
        risk=find_path.risk,
    )
    registry.register(
        open_path.name,
        open_path.execute,
        risk=open_path.risk_for,
    )
    registry.register(
        read_text_file.name,
        read_text_file.execute,
        risk=read_text_file.risk_for,
    )
    registry.register(
        read_text_lines.name,
        read_text_lines.execute,
        risk=read_text_lines.risk_for,
    )
    registry.register(
        search_text.name,
        search_text.execute,
        risk=search_text.risk,
        confirmation_preview=search_text.confirmation_preview,
    )
    registry.register(
        replace_text_literal.name,
        replace_text_literal.execute,
        risk=replace_text_literal.risk_for,
        confirmation_preview=replace_text_literal.confirmation_preview,
    )
    registry.register(
        replace_text_block.name,
        replace_text_block.execute,
        risk=replace_text_block.risk_for,
        confirmation_preview=replace_text_block.confirmation_preview,
    )
    registry.register(
        write_text_file.name,
        write_text_file.execute,
        risk=write_text_file.risk_for,
        confirmation_preview=write_text_file.confirmation_preview,
    )
    registry.register(
        create_directory.name,
        create_directory.execute,
        risk=create_directory.risk_for,
        confirmation_preview=create_directory.confirmation_preview,
    )
    registry.register(
        copy_path.name,
        copy_path.execute,
        risk=copy_path.risk_for,
        confirmation_preview=copy_path.confirmation_preview,
    )
    registry.register(
        move_path.name,
        move_path.execute,
        risk=move_path.risk_for,
        confirmation_preview=move_path.confirmation_preview,
    )
    registry.register(
        trash_path.name,
        trash_path.execute,
        risk=trash_path.risk_for,
        confirmation_preview=trash_path.confirmation_preview,
    )
    registry.register(
        system_status.name,
        system_status.execute,
        risk=system_status.risk,
    )
    registry.register(
        process_snapshot.name,
        process_snapshot.execute,
        risk=process_snapshot.risk,
        confirmation_preview=process_snapshot.confirmation_preview,
    )
    registry.register(
        terminate_process.name,
        terminate_process.execute,
        risk=terminate_process.risk,
        confirmation_preview=terminate_process.confirmation_preview,
    )
    registry.register(
        window_snapshot.name,
        window_snapshot.execute,
        risk=window_snapshot.risk,
        confirmation_preview=window_snapshot.confirmation_preview,
    )
    registry.register(
        window_snapshot_many.name,
        window_snapshot_many.execute,
        risk=window_snapshot_many.risk,
        confirmation_preview=window_snapshot_many.confirmation_preview,
    )
    registry.register(
        semantic_window_snapshot.name,
        semantic_window_snapshot.execute,
        risk=semantic_window_snapshot.risk,
        confirmation_preview=semantic_window_snapshot.confirmation_preview,
    )
    registry.register(
        invoke_semantic_button.name,
        invoke_semantic_button.execute,
        risk=invoke_semantic_button.risk,
        confirmation_preview=invoke_semantic_button.confirmation_preview,
    )
    registry.register(
        select_semantic_radio_button.name,
        select_semantic_radio_button.execute,
        risk=select_semantic_radio_button.risk,
        confirmation_preview=select_semantic_radio_button.confirmation_preview,
    )
    registry.register(
        set_semantic_checkbox_state.name,
        set_semantic_checkbox_state.execute,
        risk=set_semantic_checkbox_state.risk,
        confirmation_preview=set_semantic_checkbox_state.confirmation_preview,
    )
    registry.register(
        set_semantic_combo_box_index.name,
        set_semantic_combo_box_index.execute,
        risk=set_semantic_combo_box_index.risk,
        confirmation_preview=set_semantic_combo_box_index.confirmation_preview,
    )
    registry.register(
        set_semantic_list_box_index.name,
        set_semantic_list_box_index.execute,
        risk=set_semantic_list_box_index.risk,
        confirmation_preview=set_semantic_list_box_index.confirmation_preview,
    )
    registry.register(
        set_semantic_text.name,
        set_semantic_text.execute,
        risk=set_semantic_text.risk,
        confirmation_preview=set_semantic_text.confirmation_preview,
    )
    registry.register(
        activate_window.name,
        activate_window.execute,
        risk=activate_window.risk,
    )
    registry.register(
        move_cursor_window_anchor.name,
        move_cursor_window_anchor.execute,
        risk=move_cursor_window_anchor.risk_for,
        confirmation_preview=move_cursor_window_anchor.confirmation_preview,
    )
    registry.register(
        click_window.name,
        click_window.execute,
        risk=click_window.risk_for,
        confirmation_preview=click_window.confirmation_preview,
    )
    registry.register(
        click_window_anchor.name,
        click_window_anchor.execute,
        risk=click_window_anchor.risk_for,
        confirmation_preview=click_window_anchor.confirmation_preview,
    )
    registry.register(
        double_click_window.name,
        double_click_window.execute,
        risk=double_click_window.risk_for,
        confirmation_preview=double_click_window.confirmation_preview,
    )
    registry.register(
        double_click_window_anchor.name,
        double_click_window_anchor.execute,
        risk=double_click_window_anchor.risk_for,
        confirmation_preview=double_click_window_anchor.confirmation_preview,
    )
    registry.register(
        drag_window_anchor.name,
        drag_window_anchor.execute,
        risk=drag_window_anchor.risk_for,
        confirmation_preview=drag_window_anchor.confirmation_preview,
    )
    registry.register(
        scroll_window_anchor.name,
        scroll_window_anchor.execute,
        risk=scroll_window_anchor.risk_for,
        confirmation_preview=scroll_window_anchor.confirmation_preview,
    )
    registry.register(
        scroll_window.name,
        scroll_window.execute,
        risk=scroll_window.risk_for,
        confirmation_preview=scroll_window.confirmation_preview,
    )
    registry.register(
        press_key.name,
        press_key.execute,
        risk=press_key.risk_for,
        confirmation_preview=press_key.confirmation_preview,
    )
    registry.register(
        press_shortcut.name,
        press_shortcut.execute,
        risk=press_shortcut.risk_for,
        confirmation_preview=press_shortcut.confirmation_preview,
    )
    registry.register(
        type_text.name,
        type_text.execute,
        risk=type_text.risk,
        confirmation_preview=type_text.confirmation_preview,
    )
    registry.register(
        place_window.name,
        place_window.execute,
        risk=place_window.risk_for,
    )
    registry.register(
        place_window_pair.name,
        place_window_pair.execute,
        risk=place_window_pair.risk_for,
    )
    registry.register(
        place_window_set.name,
        place_window_set.execute,
        risk=place_window_set.risk_for,
    )
    registry.register(
        restore_window.name,
        restore_window.execute,
        risk=restore_window.risk,
    )
    registry.register(
        maximize_window.name,
        maximize_window.execute,
        risk=maximize_window.risk,
    )
    registry.register(
        minimize_window.name,
        minimize_window.execute,
        risk=minimize_window.risk,
    )
    registry.register(
        close_window.name,
        close_window.execute,
        risk=close_window.risk,
        confirmation_preview=close_window.confirmation_preview,
    )
    return registry


def build_tool_catalog() -> ToolCatalog:
    # Normal LYRA runtime: assistant capabilities only.
    return build_assistant_tool_catalog()


def build_memory_service() -> MemoryService:
    return MemoryService(SQLiteMemoryStore())


def build_ai_provider() -> AIProvider:
    return create_ai_provider()
