from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from theos.core.actions.contracts import ActionRequest, ActionResult, ActionRisk
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
from theos.lyra.execution.composed_workflow import (
    ComposedWorkflowState,
    summarize_composed_workflow,
)
from theos.lyra.execution.control import ExecutionControl
from theos.lyra.execution.file_workflow import (
    FileWorkflowState,
    summarize_file_workflow,
)
from theos.lyra.execution.run_state import LyraRunState, RunStatus
from theos.lyra.execution.workflow_progress import (
    WorkflowProgressState,
    summarize_workflow_progress,
)
from theos.lyra.perception import (
    PerceptionContext,
    compose_perception_provider_text,
)

MAX_TOOL_LOOP_STEPS = 4
ProgressCallback = Callable[[str], None]
RunStateCallback = Callable[[LyraRunState], None]

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
    run_state: LyraRunState
    application_launch_allowed: bool = False

    def __post_init__(self) -> None:
        if self.call.call_id is None:
            raise ValueError("pending tool call must contain call_id")
        if self.completed_steps < 0 or self.completed_steps >= MAX_TOOL_LOOP_STEPS:
            raise ValueError("completed_steps is out of range")
        if self.run_state.status is not RunStatus.AWAITING_CONFIRMATION:
            raise ValueError("pending confirmation requires awaiting run state")
        if self.run_state.completed_steps != self.completed_steps:
            raise ValueError("pending completed_steps do not match run state")
        if self.run_state.current_request_id != self.request.request_id:
            raise ValueError("pending run state request does not match")
        if self.run_state.current_action != self.request.action:
            raise ValueError("pending run state action does not match")


@dataclass(frozen=True, slots=True)
class ToolLoopResult:
    success: bool
    messages: tuple[str, ...]
    final_reply: str | None
    completed_steps: int
    run_state: LyraRunState
    error: str | None = None
    pending_confirmation: PendingActionConfirmation | None = None

    def __post_init__(self) -> None:
        if self.completed_steps < 0 or self.completed_steps > MAX_TOOL_LOOP_STEPS:
            raise ValueError("completed_steps is out of range")
        if self.completed_steps != self.run_state.completed_steps:
            raise ValueError("completed_steps do not match run state")
        if self.success and self.error is not None:
            raise ValueError("successful tool loop cannot contain an error")
        if self.success and self.pending_confirmation is not None:
            raise ValueError("successful tool loop cannot be pending confirmation")
        if self.error is not None and self.pending_confirmation is not None:
            raise ValueError("failed tool loop cannot be both errored and pending")
        if self.success and self.run_state.status is not RunStatus.COMPLETED:
            raise ValueError("successful tool loop requires completed run state")
        if self.pending_confirmation is not None:
            if self.run_state.status is not RunStatus.AWAITING_CONFIRMATION:
                raise ValueError("pending tool loop requires awaiting run state")
            if self.pending_confirmation.run_state != self.run_state:
                raise ValueError(
                    "pending confirmation run state must match result"
                )
        if self.error is not None and self.run_state.status not in {
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            raise ValueError(
                "errored tool loop requires failed or cancelled run state"
            )

    @property
    def awaiting_confirmation(self) -> bool:
        return self.pending_confirmation is not None

    @property
    def file_workflow(self) -> FileWorkflowState | None:
        return summarize_file_workflow(self.run_state)

    @property
    def composed_workflow(self) -> ComposedWorkflowState | None:
        return summarize_composed_workflow(self.run_state)

    @property
    def workflow_progress(self) -> WorkflowProgressState:
        return summarize_workflow_progress(self.run_state)


class ToolLoopExecutor:
    """Runs a bounded provider -> local tool -> provider loop with local risk gates."""

    def __init__(
        self,
        provider: AIProvider,
        actions: ActionRegistry,
        tools: ToolCatalog,
        *,
        max_steps: int = MAX_TOOL_LOOP_STEPS,
        perception: PerceptionContext | None = None,
    ) -> None:
        if max_steps < 1 or max_steps > MAX_TOOL_LOOP_STEPS:
            raise ValueError(f"max_steps must be between 1 and {MAX_TOOL_LOOP_STEPS}")
        self._provider = provider
        self._actions = actions
        self._tools = tools
        self._max_steps = max_steps
        self._perception = perception

    def execute(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
        tools: tuple[ToolDefinition, ...] = (),
        control: ExecutionControl | None = None,
        progress: ProgressCallback | None = None,
        state: RunStateCallback | None = None,
    ) -> ToolLoopResult:
        run_state = LyraRunState.start(
            text,
            max_steps=self._max_steps,
        )
        self._emit_state(state, run_state)

        cancelled = self._checkpoint(
            control,
            completed_steps=0,
            messages=[],
            run_state=run_state,
            state=state,
        )
        if cancelled is not None:
            return cancelled

        application_launch_allowed = _explicit_application_launch_requested(text)
        visible_tools = _visible_tools_for_request(
            tools,
            application_launch_allowed=application_launch_allowed,
        )

        provider_text = compose_perception_provider_text(
            text,
            () if self._perception is None else self._perception.snapshot(),
        )

        try:
            response = self._provider.respond(
                provider_text,
                history=history,
                tools=visible_tools,
            )
        except AIProviderError as exception:
            return self._failure(
                str(exception),
                run_state=run_state,
                state=state,
            )

        return self._drive(
            response,
            completed_steps=0,
            messages=[],
            control=control,
            progress=progress,
            state=state,
            run_state=run_state,
            application_launch_allowed=application_launch_allowed,
        )

    def resume(
        self,
        pending: PendingActionConfirmation,
        *,
        approved: bool,
        control: ExecutionControl | None = None,
        progress: ProgressCallback | None = None,
        state: RunStateCallback | None = None,
    ) -> ToolLoopResult:
        run_state = pending.run_state

        if not approved:
            error = "Ação cancelada pelo usuário."
            cancelled_state = run_state.cancel(error)
            self._emit_state(state, cancelled_state)
            return ToolLoopResult(
                success=False,
                messages=(),
                final_reply=None,
                completed_steps=pending.completed_steps,
                run_state=cancelled_state,
                error=error,
            )

        run_state = run_state.resume_after_confirmation()
        self._emit_state(state, run_state)

        cancelled = self._checkpoint(
            control,
            completed_steps=pending.completed_steps,
            messages=[],
            run_state=run_state,
            state=state,
        )
        if cancelled is not None:
            return cancelled

        result = self._execute_request(
            pending.request,
            completed_steps=pending.completed_steps,
            progress=progress,
            state=state,
            run_state=run_state,
        )
        messages = list(result.messages)
        run_state = result.run_state

        if not result.action_result.success:
            return self._failure(
                "Plano interrompido porque uma ação falhou na verificação.",
                run_state=run_state,
                messages=messages,
                state=state,
            )

        cancelled = self._checkpoint(
            control,
            completed_steps=result.completed_steps,
            messages=messages,
            run_state=run_state,
            state=state,
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
            return self._failure(
                str(exception),
                run_state=run_state,
                messages=messages,
                state=state,
            )

        return self._drive(
            response,
            completed_steps=result.completed_steps,
            messages=messages,
            control=control,
            progress=progress,
            state=state,
            run_state=run_state,
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
        state: RunStateCallback | None,
        run_state: LyraRunState,
        application_launch_allowed: bool,
    ) -> ToolLoopResult:
        while True:
            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
                run_state=run_state,
                state=state,
            )
            if cancelled is not None:
                return cancelled

            if not isinstance(response, AIToolTurn):
                break

            if completed_steps >= self._max_steps:
                return self._failure(
                    f"O plano excedeu o limite de {self._max_steps} ações por pedido.",
                    run_state=run_state,
                    messages=messages,
                    state=state,
                )

            if len(response.calls) != 1:
                return self._failure(
                    "O provedor retornou mais de uma ação na mesma etapa serial.",
                    run_state=run_state,
                    messages=messages,
                    state=state,
                )

            call = response.calls[0]
            prepared = self._prepare_call(
                call,
                application_launch_allowed=application_launch_allowed,
            )
            if isinstance(prepared, str):
                return self._failure(
                    prepared,
                    run_state=run_state,
                    messages=messages,
                    state=state,
                )

            risk = self._actions.risk_for(prepared)
            if requires_confirmation(risk):
                pending_state = run_state.wait_for_confirmation(prepared)
                self._emit_state(state, pending_state)
                pending = PendingActionConfirmation(
                    turn=response,
                    call=call,
                    request=prepared,
                    risk=risk,
                    completed_steps=completed_steps,
                    run_state=pending_state,
                    application_launch_allowed=application_launch_allowed,
                )
                return ToolLoopResult(
                    success=False,
                    messages=tuple(messages),
                    final_reply=None,
                    completed_steps=completed_steps,
                    run_state=pending_state,
                    pending_confirmation=pending,
                )

            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
                run_state=run_state,
                state=state,
            )
            if cancelled is not None:
                return cancelled

            result = self._execute_request(
                prepared,
                completed_steps=completed_steps,
                progress=progress,
                state=state,
                run_state=run_state,
            )
            messages.extend(result.messages)
            completed_steps = result.completed_steps
            run_state = result.run_state

            if not result.action_result.success:
                return self._failure(
                    "Plano interrompido porque uma ação falhou na verificação.",
                    run_state=run_state,
                    messages=messages,
                    state=state,
                )

            cancelled = self._checkpoint(
                control,
                completed_steps=completed_steps,
                messages=messages,
                run_state=run_state,
                state=state,
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
                return self._failure(
                    str(exception),
                    run_state=run_state,
                    messages=messages,
                    state=state,
                )

        if not isinstance(response, AIReply):
            return self._failure(
                "A IA retornou um resultado que não reconheço.",
                run_state=run_state,
                messages=messages,
                state=state,
            )

        completed_state = run_state.complete(response.text)
        self._emit_state(state, completed_state)

        return ToolLoopResult(
            success=True,
            messages=tuple(messages),
            final_reply=response.text,
            completed_steps=completed_steps,
            run_state=completed_state,
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
        action_result: ActionResult
        run_state: LyraRunState

    def _execute_request(
        self,
        request: ActionRequest,
        *,
        completed_steps: int,
        progress: ProgressCallback | None,
        state: RunStateCallback | None,
        run_state: LyraRunState,
    ) -> _Execution:
        if run_state.current_request_id != request.request_id:
            run_state = run_state.begin_action(request)
            self._emit_state(state, run_state)

        opening = self._progress_message(request)
        self._emit_progress(progress, opening)

        action_result = self._actions.execute(request)
        if self._perception is not None:
            self._perception.record(request, action_result)
        run_state = run_state.record_action(request, action_result)
        self._emit_state(state, run_state)

        completed_steps = run_state.completed_steps
        completed = f"Etapa {completed_steps}: {action_result.message}"
        self._emit_progress(progress, completed)

        return self._Execution(
            messages=(opening, completed),
            completed_steps=completed_steps,
            action_result=action_result,
            run_state=run_state,
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
        if request.action == "check_python_syntax":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Verificando sintaxe Python em {target}..."
        if request.action == "check_python_static":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Analisando Python estaticamente em {target}..."
        if request.action == "check_python_static_many":
            paths = request.arguments.get("paths", [])
            count = len(paths) if isinstance(paths, list) else 0
            return f"Analisando estaticamente {count} arquivos Python..."
        if request.action == "run_python_unit_test_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Executando teste unitário Python {target}..."
        if request.action == "run_python_unit_test_files":
            paths = request.arguments.get("paths", [])
            count = len(paths) if isinstance(paths, list) else 0
            return f"Executando lote de {count} arquivos de teste Python..."
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
        if request.action == "replace_text_block":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Substituindo bloco literal em {target}..."
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
        if request.action == "git_commit_staged_new_file":
            return "Criando commit Git local do único arquivo novo staged..."
        if request.action == "git_commit_staged_file":
            return "Criando commit Git local do único arquivo staged..."
        if request.action == "git_diff_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Inspecionando diff Git de {target}..."
        if request.action == "git_stage_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Preparando stage Git de {target}..."
        if request.action == "git_stage_new_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Preparando stage Git de novo arquivo {target}..."
        if request.action == "git_unstage_new_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Removendo stage Git de novo arquivo {target}..."
        if request.action == "git_unstage_file":
            target = str(request.arguments.get("path", "arquivo"))
            return f"Removendo stage Git de {target}..."
        if request.action == "git_fetch_remote_main":
            return "Atualizando snapshot local de origin/main..."
        if request.action == "git_remote_head_snapshot":
            return "Lendo HEAD remoto Git autorizado..."
        if request.action == "git_remote_identity_snapshot":
            return "Validando identidade Git remota local..."
        if request.action == "git_status_snapshot":
            return "Inspecionando status Git local..."
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
        run_state: LyraRunState,
        state: RunStateCallback | None,
    ) -> ToolLoopResult | None:
        if control is None or control.checkpoint():
            return None

        error = "Tarefa cancelada pelo usuário."
        cancelled_state = run_state.cancel(error)
        ToolLoopExecutor._emit_state(state, cancelled_state)
        return ToolLoopResult(
            success=False,
            messages=tuple(messages),
            final_reply=None,
            completed_steps=completed_steps,
            run_state=cancelled_state,
            error=error,
        )

    @staticmethod
    def _emit_progress(
        progress: ProgressCallback | None,
        message: str,
    ) -> None:
        if progress is not None:
            progress(message)

    @staticmethod
    def _emit_state(
        state: RunStateCallback | None,
        run_state: LyraRunState,
    ) -> None:
        if state is not None:
            state(run_state)

    @staticmethod
    def _failure(
        message: str,
        *,
        run_state: LyraRunState,
        messages: list[str] | tuple[str, ...] = (),
        state: RunStateCallback | None = None,
    ) -> ToolLoopResult:
        failed_state = run_state.fail(message)
        ToolLoopExecutor._emit_state(state, failed_state)
        return ToolLoopResult(
            success=False,
            messages=tuple(messages),
            final_reply=None,
            completed_steps=failed_state.completed_steps,
            run_state=failed_state,
            error=message,
        )
