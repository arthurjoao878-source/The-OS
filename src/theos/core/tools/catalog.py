from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from theos.core.actions.contracts import ActionRequest
from theos.core.tools.contracts import ToolCall, ToolDefinition, ToolValidationError

ArgumentValidator = Callable[[Mapping[str, object]], dict[str, object]]


@dataclass(frozen=True, slots=True)
class _ToolRegistration:
    definition: ToolDefinition
    validate: ArgumentValidator


class ToolCatalog:
    """Local allowlist that turns validated model proposals into ActionRequests."""

    def __init__(self) -> None:
        self._registrations: dict[str, _ToolRegistration] = {}

    def register(
        self,
        definition: ToolDefinition,
        validator: ArgumentValidator,
    ) -> None:
        if definition.name in self._registrations:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._registrations[definition.name] = _ToolRegistration(
            definition=definition,
            validate=validator,
        )

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            registration.definition
            for registration in self._registrations.values()
        )

    def build_action_request(self, call: ToolCall) -> ActionRequest:
        registration = self._registrations.get(call.name)
        if registration is None:
            raise ToolValidationError(f"Tool not allowed: {call.name}")

        arguments = registration.validate(call.arguments)
        return ActionRequest(
            action=registration.definition.name,
            arguments=arguments,
        )


def build_default_tool_catalog() -> ToolCatalog:
    catalog = ToolCatalog()
    catalog.register(
        ToolDefinition(
            name="open_application",
            description=(
                "Abre um aplicativo instalado no computador Windows do usuário. "
                "Use quando o usuário pedir para abrir, iniciar ou executar um aplicativo."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "Nome do aplicativo que o usuário quer abrir.",
                    }
                },
                "required": ["application"],
                "additionalProperties": False,
            },
        ),
        _validate_open_application,
    )
    return catalog


def _validate_open_application(arguments: Mapping[str, object]) -> dict[str, object]:
    if set(arguments) != {"application"}:
        raise ToolValidationError("open_application requires only 'application'")

    application = arguments.get("application")
    if not isinstance(application, str) or not application.strip():
        raise ToolValidationError("application must be a non-blank string")

    return {"application": application.strip()}
