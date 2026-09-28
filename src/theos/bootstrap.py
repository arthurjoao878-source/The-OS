from __future__ import annotations

from theos.core.actions.desktop_windows import (
    ActivateWindowAction,
    CloseWindowAction,
    MaximizeWindowAction,
    MinimizeWindowAction,
    PressKeyAction,
    RestoreWindowAction,
    TypeTextAction,
    WindowSnapshotAction,
)
from theos.core.actions.file_system import (
    CopyPathAction,
    CreateDirectoryAction,
    FindPathAction,
    InspectPathAction,
    MovePathAction,
    OpenPathAction,
    ReadTextFileAction,
    TrashPathAction,
    WriteTextFileAction,
)
from theos.core.actions.open_application import OpenApplicationAction
from theos.core.actions.processes import ProcessSnapshotAction, TerminateProcessAction
from theos.core.actions.registry import ActionRegistry
from theos.core.actions.system_status import SystemStatusAction
from theos.core.applications.registry import ApplicationRegistry
from theos.core.tools import ToolCatalog, build_default_tool_catalog
from theos.integrations.ai import AIProvider
from theos.integrations.ai import build_ai_provider as create_ai_provider
from theos.integrations.windows.applications import WindowsApplicationAdapter
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.integrations.windows.processes import WindowsProcessAdapter
from theos.integrations.windows.system_status import WindowsSystemStatusAdapter
from theos.lyra.memory.service import MemoryService
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


def build_action_registry() -> ActionRegistry:
    applications = ApplicationRegistry()
    windows_applications = WindowsApplicationAdapter()
    windows_desktop = WindowsDesktopWindowAdapter()
    windows_files = WindowsFileSystemAdapter()
    windows_processes = WindowsProcessAdapter()
    windows_system = WindowsSystemStatusAdapter()

    open_application = OpenApplicationAction(applications, windows_applications)
    inspect_path = InspectPathAction(windows_files)
    find_path = FindPathAction(windows_files)
    open_path = OpenPathAction(windows_files)
    read_text_file = ReadTextFileAction(windows_files)
    write_text_file = WriteTextFileAction(windows_files)
    create_directory = CreateDirectoryAction(windows_files)
    copy_path = CopyPathAction(windows_files)
    move_path = MovePathAction(windows_files)
    trash_path = TrashPathAction(windows_files)
    process_snapshot = ProcessSnapshotAction(windows_processes)
    terminate_process = TerminateProcessAction(windows_processes)
    window_snapshot = WindowSnapshotAction(windows_desktop)
    activate_window = ActivateWindowAction(windows_desktop)
    press_key = PressKeyAction(windows_desktop)
    type_text = TypeTextAction(windows_desktop)
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
        activate_window.name,
        activate_window.execute,
        risk=activate_window.risk,
    )
    registry.register(
        press_key.name,
        press_key.execute,
        risk=press_key.risk_for,
        confirmation_preview=press_key.confirmation_preview,
    )
    registry.register(
        type_text.name,
        type_text.execute,
        risk=type_text.risk,
        confirmation_preview=type_text.confirmation_preview,
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
    return build_default_tool_catalog()


def build_memory_service() -> MemoryService:
    return MemoryService(SQLiteMemoryStore())


def build_ai_provider() -> AIProvider:
    return create_ai_provider()
