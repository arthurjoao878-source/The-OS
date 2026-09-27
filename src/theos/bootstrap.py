from __future__ import annotations

from theos.core.actions.file_system import (
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
from theos.core.actions.registry import ActionRegistry
from theos.core.applications.registry import ApplicationRegistry
from theos.core.tools import ToolCatalog, build_default_tool_catalog
from theos.integrations.ai import AIProvider
from theos.integrations.ai import build_ai_provider as create_ai_provider
from theos.integrations.windows.applications import WindowsApplicationAdapter
from theos.integrations.windows.file_system import WindowsFileSystemAdapter
from theos.lyra.memory.service import MemoryService
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


def build_action_registry() -> ActionRegistry:
    applications = ApplicationRegistry()
    windows_applications = WindowsApplicationAdapter()
    windows_files = WindowsFileSystemAdapter()

    open_application = OpenApplicationAction(applications, windows_applications)
    inspect_path = InspectPathAction(windows_files)
    find_path = FindPathAction(windows_files)
    open_path = OpenPathAction(windows_files)
    read_text_file = ReadTextFileAction(windows_files)
    write_text_file = WriteTextFileAction(windows_files)
    create_directory = CreateDirectoryAction(windows_files)
    move_path = MovePathAction(windows_files)
    trash_path = TrashPathAction(windows_files)

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
    return registry


def build_tool_catalog() -> ToolCatalog:
    return build_default_tool_catalog()


def build_memory_service() -> MemoryService:
    return MemoryService(SQLiteMemoryStore())


def build_ai_provider() -> AIProvider:
    return create_ai_provider()
