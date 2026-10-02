from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.policy import requires_confirmation
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCall, ToolCatalog, ToolDefinition, ToolValidationError
from theos.integrations.ai import (
    AIProvider,
    AIProviderError,
    AIReply,
    AIToolResult,
    AIToolTurn,
)
from theos.lyra.context import ConversationTurn
from theos.lyra.execution.control import ExecutionControl

MAX_TOOL_LOOP_STEPS = 4
ProgressCallback = Callable[[str], None]

_APPLICATION_LAUNCH_RE = re.compile(
    r"\b(?:abre|abra|abrir|inicia|inicie|iniciar|execute|executa|executar|"
    r"rode|rodar|reabra|reabrir|reinicie|reiniciar|open|start|launch|reopen)\b",
    re.IGNORECASE,
)
_APPLICATION_LAUNCH_NEGATION_RE = re.compile(
    r"\b(?:não|nao|never|don't|dont|do\s+not)\b",
    re.IGNORECASE,
)


def _explicit_application_launch_requested(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False

    for match in _APPLICATION_LAUNCH_RE.finditer(normalized):
        clause_start = max(
            normalized.rfind(separator, 0, match.start())
            for separator in (",", ";", ".", "!", "?", "\n")
        )
        prefix = normalized[clause_start + 1 : match.start()]
        if _APPLICATION_LAUNCH_NEGATION_RE.search(prefix):
            continue
        return True
    return False


def _visible_tools_for_request(
    tools: tuple[ToolDefinition, ...],
    *,
    application_launch_allowed: bool,
) -> tuple[ToolDefinition, ...]:
    if application_launch_allowed:
        return tools
    return tuple(
        definition
        for definition in tools
        if definition.name != "open_application"
    )


@dataclass(frozen=True, slots=True)
class PendingActionConfirmation:
    turn: AIToolTurn
    call: ToolCall
    request: ActionRequest
    risk: ActionRisk
    completed_steps: int
    application_launch_allowed: bool = False

    def __post_init__(self) -> None:
        if self.call.call_id is None:
            raise ValueError("pending tool call must contain call_id")
        if self.completed_steps < 0 or self.completed_steps >= MAX_TOOL_LOOP_STEPS:
            raise ValueError("completed_steps is out of range")


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    success: bool
    messages: tuple[str, ...]
    final_reply: str | None
    completed_steps: int
    error: str | None = None
    pending_confirmation: PendingActionConfirmation | None = None

    def __post_init__(self) -> None:
        if self.completed_steps < 0 or self.completed_steps > MAX_TOOL_LOOP_STEPS:
            raise ValueError("completed_steps is out of range")
        if self.success and self.error is not None:
            raise ValueError("successful tool loop cannot contain an error")
        if self.success and self.pending_confirmation is not None:
            raise ValueError("successful tool loop cannot be pending confirmation")
        if self.error is not None and self.pending_confirmation is not None:
            raise ValueError("failed tool loop cannot be both errored and pending")

    @property
    def awaiting_confirmation(self) -> bool:
        return self.pending_confirmation is not None


class ToolLoopExecutor:
    """Runs a bounded provider -> local tool -> provider loop with local risk gates."""

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
        control: ExecutionControl | None = None,
        progress: ProgressCallback | None = None,
    ) -> ToolLoopResult:
        cancelled = self._checkpoint(
            control,
            completed_steps=0,
            messages=[],
        )
        if cancelled is not None:
            return cancelled

        application_launch_allowed = _explicit_application_launch_requested(text)
        visible_tools = _visible_tools_for_request(
            tools,
            application_launch_allowed=application_launch_allowed,
        )

        try:
            response = self._provider.respond(
                text,
                history=history,
                tools=visible_tools,
            )
        except AIProviderError as exception:
            return self._failure(str(exception), completed_steps=0)

        return self._drive(
            response,
            completed_steps=0,
            messages=[],
            control=control,
            progress=progress,
            application_launch_allowed=application_launch_allowed,
        )

    def resume(
        self,
        pending: PendingActionConfirmation,
        *,
        approved: bool,
        control: ExecutionControl | None = None,
        progress: ProgressCallback | None = None,
    ) -> ToolLoopResult:
        if not approved:
            return ToolLoopResult(
                success=False,
                messages=(),
                final_reply=None,
                completed_steps=pending.completed_steps,
                error="Ação cancelada pelo usuário.",
            )

        cancelled = self._checkpoint(
            control,
            completed_steps=pending.completed_steps,
            messages=[],
        )
        if cancelled is not None:
            return cancelled

        result = self._execute_request(
            pending.request,
            completed_steps=pending.completed_steps,
            progress=progress,
        )
        messages = list(result.messages)
        if result.action_result is None:
            return ToolLoopResult(
                success=False,
                messages=tuple(messages),
                final_reply=None,
                completed_steps=result.completed_steps,
                error=result.error,
            )

        if not result.action_result.success:
            return ToolLoopResult(
                success=False,
                messages=tuple(messages),
                final_reply=None,
                completed_steps=result.completed_steps,
                error="Plano interrompido porque uma ação falhou na verificação.",
            )

        cancelled = self._checkpoint(
            control,
            completed_steps=result.completed_steps,
            messages=messages,
        )
        if cancelled is not None:
            return cancelled

        output = self._tool_output(
            pending.call,
            result.action_result,
        )
        try:
            response = self._provider.continue_after_tools(
                pending.turn,
                (output,),
            )
        except AIProviderError as exception:
            return ToolLoopResult(
                success=False,
                messages=tuple(messages),
                final_reply=None,
                completed_steps=result.completed_steps,
                error=str(exception),
            )

        return self._drive(
            response,
            completed_steps=result.completed_steps,
            messages=messages,
            control=control,
            progress=progress,
            application_launch_allowed=pending.application_launch_allowed,
        )

    def _drive(
        self,
        response: object,
        *,
        completed_steps: int,
        messages: list[str],
        control: ExecutionControl | None,
        progress: ProgressCallback | None,
        application_launch_allowed: bool,
    ) -> ToolLoopResult:
        while True:
            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
            )
            if cancelled is not None:
                return cancelled

            if not isinstance(response, AIToolTurn):
                break

            if completed_steps >= self._max_steps:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error=f"O plano excedeu o limite de {self._max_steps} ações por pedido.",
                )

            if len(response.calls) != 1:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error="O provedor retornou mais de uma ação na mesma etapa serial.",
                )

            call = response.calls[0]
            prepared = self._prepare_call(
                call,
                application_launch_allowed=application_launch_allowed,
            )
            if isinstance(prepared, str):
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error=prepared,
                )

            risk = self._actions.risk_for(prepared)
            if requires_confirmation(risk):
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    pending_confirmation=PendingActionConfirmation(
                        turn=response,
                        call=call,
                        request=prepared,
                        risk=risk,
                        completed_steps=completed_steps,
                        application_launch_allowed=application_launch_allowed,
                    ),
                )

            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
            )
            if cancelled is not None:
                return cancelled

            result = self._execute_request(
                prepared,
                completed_steps=completed_steps,
                progress=progress,
            )
            messages.extend(result.messages)
            completed_steps = result.completed_steps

            if result.action_result is None:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error=result.error,
                )

            if not result.action_result.success:
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    error="Plano interrompido porque uma ação falhou na verificação.",
                )

            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
            )
            if cancelled is not None:
                return cancelled

            output = self._tool_output(call, result.action_result)
            try:
                response = self._provider.continue_after_tools(
                    response,
                    (output,),
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

    def _prepare_call(
        self,
        call: ToolCall,
        *,
        application_launch_allowed: bool,
    ) -> ActionRequest | str:
        if call.call_id is None:
            return "A IA retornou uma ferramenta sem call_id."
        if call.name == "open_application" and not application_launch_allowed:
            return (
                "A IA propôs abrir um aplicativo sem pedido explícito do usuário "
                "para abrir, iniciar ou executar uma nova instância."
            )
        if not self._actions.contains(call.name):
            return "A IA propôs uma ação que não está registrada."

        try:
            return self._tools.build_action_request(call)
        except ToolValidationError:
            return "A IA propôs argumentos inválidos para uma ação."

    @dataclass(frozen=True, slots=True)
    class _Execution:
        messages: tuple[str, ...]
        completed_steps: int
        action_result: object | None
        error: str | None = None

    def _execute_request(
        self,
        request: ActionRequest,
        *,
        completed_steps: int,
        progress: ProgressCallback | None,
    ) -> _Execution:
        opening = self._progress_message(request)
        self._emit_progress(progress, opening)

        action_result = self._actions.execute(request)
        completed_steps += 1
        completed = f"Etapa {completed_steps}: {action_result.message}"
        self._emit_progress(progress, completed)

        return self._Execution(
            messages=(opening, completed),
            completed_steps=completed_steps,
            action_result=action_result,
        )

    @staticmethod
    def _progress_message(request: ActionRequest) -> str:
        if request.action == "open_application":
            target = str(request.arguments.get("application", "aplicativo"))
            return f"Abrindo {target}..."
        if request.action == "inspect_path":
            target = str(request.arguments.get("path", "caminho"))
            return f"Inspecionando {target}..."
        if request.action == "find_path":
            query = str(request.arguments.get("query", "item"))
            root = str(request.arguments.get("root", "pasta"))
            return f"Procurando {query} em {root}..."
        if request.action == "search_text":
            query = str(request.arguments.get("query", "texto"))
            root = str(request.arguments.get("root", "pasta"))
            return f"Procurando texto {query} em {root}..."
        if request.action == "open_path":
            target = str(request.arguments.get("path", "caminho"))
            return f"Abrindo {target}..."
        if request.action == "read_text_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Lendo {target}..."
        if request.action == "read_text_lines":
            target = str(request.arguments.get("path", "arquivo"))
            start_line = request.arguments.get("start_line", "desconhecida")
            return f"Lendo linhas a partir de {start_line} em {target}..."
        if request.action == "write_text_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Gravando {target}..."
        if request.action == "replace_text_literal":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Substituindo texto literal em {target}..."
        if request.action == "create_directory":
            target = str(request.arguments.get("path", "pasta"))
            return f"Criando pasta {target}..."
        if request.action == "copy_path":
            source = str(request.arguments.get("source", "origem"))
            destination = str(request.arguments.get("destination", "destino"))
            return f"Copiando {source} para {destination}..."
        if request.action == "move_path":
            source = str(request.arguments.get("source", "origem"))
            destination = str(request.arguments.get("destination", "destino"))
            return f"Movendo {source} para {destination}..."
        if request.action == "trash_path":
            target = str(request.arguments.get("path", "caminho"))
            return f"Enviando {target} para a Lixeira..."
        if request.action == "system_status":
            return "Coletando status do sistema..."
        if request.action == "process_snapshot":
            return "Inspecionando processos em execução..."
        if request.action == "terminate_process":
            pid = request.arguments.get("pid", "desconhecido")
            return f"Encerrando processo PID {pid}..."
        if request.action == "window_snapshot":
            return "Inspecionando janelas visíveis..."
        if request.action == "activate_window":
            title = str(request.arguments.get("title", "janela"))
            return f"Ativando janela {title}..."
        if request.action == "press_key":
            title = str(request.arguments.get("title", "janela"))
            key = str(request.arguments.get("key", "tecla"))
            return f"Enviando tecla {key} para a janela {title}..."
        if request.action == "type_text":
            title = str(request.arguments.get("title", "janela"))
            return f"Enviando texto para a janela {title}..."
        if request.action == "restore_window":
            title = str(request.arguments.get("title", "janela"))
            return f"Restaurando janela {title} para o tamanho normal..."
        if request.action == "maximize_window":
            title = str(request.arguments.get("title", "janela"))
            return f"Maximizando janela {title}..."
        if request.action == "minimize_window":
            title = str(request.arguments.get("title", "janela"))
            return f"Minimizando janela {title}..."
        if request.action == "close_window":
            title = str(request.arguments.get("title", "janela"))
            return f"Fechando janela {title}..."
        return f"Executando {request.action}..."

    @staticmethod
    def _tool_output(
        call: ToolCall,
        action_result: object,
    ) -> AIToolResult:
        if call.call_id is None:
            raise ValueError("tool call must contain call_id")
        output = json.dumps(
            action_result.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return AIToolResult(
            call_id=call.call_id,
            output=output,
        )

    @staticmethod
    def _checkpoint(
        control: ExecutionControl | None,
        *,
        completed_steps: int,
        messages: list[str],
    ) -> ToolLoopResult | None:
        if control is None or control.checkpoint():
            return None
        return ToolLoopResult(
            success=False,
            messages=tuple(messages),
            final_reply=None,
            completed_steps=completed_steps,
            error="Tarefa cancelada pelo usuário.",
        )

    @staticmethod
    def _emit_progress(
        progress: ProgressCallback | None,
        message: str,
    ) -> None:
        if progress is not None:
            progress(message)

    @staticmethod
    def _failure(message: str, *, completed_steps: int) -> ToolLoopResult:
        return ToolLoopResult(
            success=False,
            messages=(),
            final_reply=None,
            completed_steps=completed_steps,
            error=message,
        )
