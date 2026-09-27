from __future__ import annotations

import json
from dataclasses import dataclass

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCatalog, ToolDefinition, ToolValidationError
from theos.integrations.ai import (
    AIProvider,
    AIProviderError,
    AIReply,
    AIToolResult,
    AIToolTurn,
)
from theos.lyra.context import ConversationTurn

MAX_TOOL_LOOP_STEPS = 4


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    success: bool
    messages: tuple[str, ...]
    final_reply: str | None
    completed_steps: int
    error: str | None = None

    def __post_init__(self) -> None:
        if self.completed_steps < 0 or self.completed_steps > MAX_TOOL_LOOP_STEPS:
            raise ValueError("completed_steps is out of range")
        if self.success and self.error is not None:
            raise ValueError("successful tool loop cannot contain an error")


class ToolLoopExecutor:
    """Runs a bounded provider -> local tool -> provider loop."""

    def __init__(
        self,
        provider: AIProvider,
        actions: ActionRegistry,
        tools: ToolCatalog,
        *,
        max_steps: int = MAX_TOOL_LOOP_STEPS,
    ) -> None:
        if max_steps < 1 or max_steps > MAX_TOOL_LOOP_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_TOOL_LOOP_STEPS}")
        self._provider = provider
        self._actions = actions
        self._tools = tools
        self._max_steps = max_steps

    def execute(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
        tools: tuple[ToolDefinition, ...] = (),
    ) -> ToolLoopResult:
        try:
            response = self._provider.respond(text, history=history, tools=tools)
        except AIProviderError as exception:
            return self._failure(str(exception), completed_steps=0)

        messages: list[str] = []
        completed_steps = 0

        while isinstance(response, AIToolTurn):
            if completed_steps + len(response.calls) > self._max_steps:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error=f"O plano excedeu o limite de {self._max_steps} ações por pedido.",
                )

            prepared: list[tuple[object, object]] = []
            for call in response.calls:
                if call.call_id is None:
                    return ToolLoopResult(
                        success=False,
                        messages=tuple(messages),
                        final_reply=None,
                        completed_steps=completed_steps,
                        error="A IA retornou uma ferramenta sem call_id.",
                    )
                if not self._actions.contains(call.name):
                    return ToolLoopResult(
                        success=False,
                        messages=tuple(messages),
                        final_reply=None,
                        completed_steps=completed_steps,
                        error="A IA propôs uma ação que não está registrada.",
                    )
                try:
                    request = self._tools.build_action_request(call)
                except ToolValidationError:
                    return ToolLoopResult(
                        success=False,
                        messages=tuple(messages),
                        final_reply=None,
                        completed_steps=completed_steps,
                        error="A IA propôs argumentos inválidos para uma ação.",
                    )
                prepared.append((call, request))

            outputs: list[AIToolResult] = []
            for call, request in prepared:
                app = str(request.arguments.get("application", "aplicativo"))
                messages.append(f"Abrindo {app}...")

                result = self._actions.execute(request)
                completed_steps += 1
                messages.append(
                    f"Etapa {completed_steps}: {result.message}"
                )

                output = json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                outputs.append(
                    AIToolResult(
                        call_id=call.call_id,
                        output=output,
                    )
                )

                if not result.success:
                    return ToolLoopResult(
                        success=False,
                        messages=tuple(messages),
                        final_reply=None,
                        completed_steps=completed_steps,
                        error="Plano interrompido porque uma ação falhou na verificação.",
                    )

            try:
                response = self._provider.continue_after_tools(
                    response,
                    tuple(outputs),
                )
            except AIProviderError as exception:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error=str(exception),
                )

        if not isinstance(response, AIReply):
            return ToolLoopResult(
                success=False,
                messages=tuple(messages),
                final_reply=None,
                completed_steps=completed_steps,
                error="A IA retornou um resultado que não reconheço.",
            )

        return ToolLoopResult(
            success=True,
            messages=tuple(messages),
            final_reply=response.text,
            completed_steps=completed_steps,
        )

    @staticmethod
    def _failure(message: str, *, completed_steps: int) -> ToolLoopResult:
        return ToolLoopResult(
            success=False,
            messages=(),
            final_reply=None,
            completed_steps=completed_steps,
            error=message,
        )
