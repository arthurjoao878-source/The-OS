from __future__ import annotations

from theos.core.actions.open_application import OpenApplicationAction
from theos.core.actions.registry import ActionRegistry
from theos.core.applications.registry import ApplicationRegistry
from theos.core.tools import ToolCatalog, build_default_tool_catalog
from theos.integrations.ai import AIProvider
from theos.integrations.ai import build_ai_provider as create_ai_provider
from theos.integrations.windows.applications import WindowsApplicationAdapter
from theos.lyra.memory.service import MemoryService
from theos.lyra.memory.sqlite_store import SQLiteMemoryStore


def build_action_registry() -> ActionRegistry:
    applications = ApplicationRegistry()
    windows = WindowsApplicationAdapter()

    open_application = OpenApplicationAction(applications, windows)

    registry = ActionRegistry()
    registry.register(
        open_application.name,
        open_application.execute,
        risk=open_application.risk_for,
    )
    return registry


def build_tool_catalog() -> ToolCatalog:
    return build_default_tool_catalog()


def build_memory_service() -> MemoryService:
    return MemoryService(SQLiteMemoryStore())


def build_ai_provider() -> AIProvider:
    return create_ai_provider()
