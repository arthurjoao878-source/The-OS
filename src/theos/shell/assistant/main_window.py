from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from theos.core.actions.contracts import ActionRequest, ActionRisk
from theos.core.actions.policy import requires_confirmation
from theos.core.actions.registry import ActionRegistry
from theos.core.tools import ToolCatalog, ToolDefinition
from theos.integrations.ai import AIProvider
from theos.lyra.context import ConversationTurn, SessionContext
from theos.lyra.execution import (
    ExecutionControl,
    ExecutionStatus,
    LyraRunState,
    PendingActionConfirmation,
    ToolLoopExecutor,
    ToolLoopResult,
)
from theos.lyra.memory.intent import MemoryIntentKind
from theos.lyra.memory.service import MemoryService
from theos.lyra.perception import PerceptionContext
from theos.lyra.personality import PersonalityContext
from theos.lyra.planning import LyraPlanner, PlanKind
from theos.shell.assistant.workflow_progress import present_run_state


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    state = Signal(object)


class ActionWorker(QRunnable):
    def __init__(self, action_registry: ActionRegistry, request: ActionRequest) -> None:
        super().__init__()
        self.action_registry = action_registry
        self.request = request
        self.signals = WorkerSignals()

    def run(self) -> None:
        result = self.action_registry.execute(self.request)
        self.signals.finished.emit(result)


class ToolLoopWorker(QRunnable):
    def __init__(
        self,
        executor: ToolLoopExecutor,
        text: str,
        history: tuple[ConversationTurn, ...],
        tools: tuple[ToolDefinition, ...],
        control: ExecutionControl,
    ) -> None:
        super().__init__()
        self.executor = executor
        self.text = text
        self.history = history
        self.tools = tools
        self.control = control
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.executor.execute(
                self.text,
                history=self.history,
                tools=self.tools,
                control=self.control,
                progress=self.signals.progress.emit,
                state=self.signals.state.emit,
            )
        except (TypeError, ValueError):
            self.signals.failed.emit("O loop de ferramentas retornou um estado inválido.")
            return
        self.signals.finished.emit(result)


class ToolLoopResumeWorker(QRunnable):
    def __init__(
        self,
        executor: ToolLoopExecutor,
        pending: PendingActionConfirmation,
        control: ExecutionControl,
        *,
        approved: bool,
    ) -> None:
        super().__init__()
        self.executor = executor
        self.pending = pending
        self.control = control
        self.approved = approved
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.executor.resume(
                self.pending,
                approved=self.approved,
                control=self.control,
                progress=self.signals.progress.emit,
                state=self.signals.state.emit,
            )
        except (TypeError, ValueError):
            self.signals.failed.emit("Não consegui retomar a ação após a confirmação.")
            return
        self.signals.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(
        self,
        action_registry: ActionRegistry,
        memory_service: MemoryService,
        ai_provider: AIProvider,
        tool_catalog: ToolCatalog,
    ) -> None:
        super().__init__()
        self._actions = action_registry
        self._memory = memory_service
        self._ai = ai_provider
        self._tools = tool_catalog
        self._planner = LyraPlanner()
        self._context = SessionContext(max_turns=12)
        self._perception = PerceptionContext(max_observations=8)
        self._personality = PersonalityContext()
        self._tool_loop = ToolLoopExecutor(
            ai_provider,
            action_registry,
            tool_catalog,
            perception=self._perception,
        )
        self._pool = QThreadPool.globalInstance()
        self._active_control: ExecutionControl | None = None

        self.setWindowTitle("LYRA — executor local: THE HANDS")
        self.resize(760, 600)

        root = QWidget()
        layout = QVBoxLayout(root)

        header = QLabel("LYRA  ● ON")
        self.workflow_status = QLabel("Tarefa: ociosa")
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Diga algo...")
        self.send = QPushButton("Enviar")

        self.pause_task = QPushButton("Pausar")
        self.resume_task = QPushButton("Retomar")
        self.cancel_task = QPushButton("Cancelar")

        composer = QHBoxLayout()
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send)

        controls = QHBoxLayout()
        controls.addWidget(self.pause_task)
        controls.addWidget(self.resume_task)
        controls.addWidget(self.cancel_task)
        controls.addStretch(1)

        layout.addWidget(header)
        layout.addWidget(self.workflow_status)
        layout.addWidget(self.chat, 1)
        layout.addLayout(composer)
        layout.addLayout(controls)

        self.setCentralWidget(root)

        self.send.clicked.connect(self._submit)
        self.input.returnPressed.connect(self._submit)
        self.pause_task.clicked.connect(self._pause_active_task)
        self.resume_task.clicked.connect(self._resume_active_task)
        self.cancel_task.clicked.connect(self._cancel_active_task)

        self._update_task_controls(None)
        self._lyra("Pronta.")

    def _you(self, text: str) -> None:
        self.chat.appendPlainText(f"Você\n{text}\n")

    def _lyra(self, text: str, *, remember_in_session: bool = False) -> None:
        self.chat.appendPlainText(f"LYRA\n{text}\n")
        if remember_in_session:
            self._context.add_assistant(text)

    def _set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def _update_task_controls(
        self,
        status: ExecutionStatus | None,
    ) -> None:
        self.pause_task.setEnabled(status is ExecutionStatus.RUNNING)
        self.resume_task.setEnabled(status is ExecutionStatus.PAUSED)
        self.cancel_task.setEnabled(
            status in {ExecutionStatus.RUNNING, ExecutionStatus.PAUSED}
        )

    def _available_ai_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            definition
            for definition in self._tools.definitions()
            if self._actions.contains(definition.name)
        )

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return

        history = self._context.snapshot()
        self._context.add_user(text)
        self.input.clear()
        self._you(text)

        plan = self._planner.plan(text)

        if plan.kind is PlanKind.MEMORY:
            memory_intent = plan.memory_intent
            if memory_intent is None:
                raise RuntimeError("memory plan missing memory intent")

            if memory_intent.kind is MemoryIntentKind.REMEMBER:
                self._memory.remember(memory_intent.text)
                self._lyra("Memória salva.", remember_in_session=True)
                return

            results = self._memory.recall(memory_intent.text, limit=3)
            if not results:
                self._lyra(
                    "Não encontrei nada na memória sobre isso.",
                    remember_in_session=True,
                )
                return
            remembered = "\n".join(
                f"• {record.content}"
                for record in results
                if record.content is not None
            )
            self._lyra(
                f"Eu lembro:\n{remembered}",
                remember_in_session=True,
            )
            return

        if plan.kind is PlanKind.ACTION:
            request = plan.action_request
            if request is None:
                raise RuntimeError("action plan missing action request")
            self._handle_direct_action(request)
            return

        self._start_tool_task(
            text,
            history,
        )

    def _start_tool_task(
        self,
        text: str,
        history: tuple[ConversationTurn, ...],
    ) -> None:
        self._lyra("Pensando...")
        self._set_busy(True)

        control = ExecutionControl()
        self._active_control = control
        self._update_task_controls(control.status)

        worker = ToolLoopWorker(
            self._tool_loop,
            text,
            history,
            self._available_ai_tools(),
            control,
        )
        worker.signals.progress.connect(self._on_tool_progress)
        worker.signals.state.connect(self._on_tool_state)
        worker.signals.finished.connect(self._on_tool_loop_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _pause_active_task(self) -> None:
        control = self._active_control
        if control is not None and control.pause():
            self._update_task_controls(control.status)
            self._lyra("Tarefa pausada.")

    def _resume_active_task(self) -> None:
        control = self._active_control
        if control is not None and control.resume():
            self._update_task_controls(control.status)
            self._lyra("Tarefa retomada.")

    def _cancel_active_task(self) -> None:
        control = self._active_control
        if control is not None and control.cancel():
            self._update_task_controls(control.status)
            self._lyra("Cancelamento solicitado.")

    def _finish_tool_task(self) -> None:
        self._active_control = None
        self._update_task_controls(None)
        self._set_busy(False)

    def _handle_direct_action(self, request: ActionRequest) -> None:
        risk = self._actions.risk_for(request)
        if requires_confirmation(risk):
            decision = self._confirm_action(request, risk)
            if decision is None:
                return
            if not decision:
                self._lyra("Ação cancelada.", remember_in_session=True)
                return

        app = str(request.arguments.get("application", "aplicativo"))
        self._lyra(f"Abrindo {app}...")
        self._start_action(request)

    @staticmethod
    def _action_subject(request: ActionRequest) -> str:
        pid = request.arguments.get("pid")
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
            return f"PID {pid}"

        for key in (
            "application",
            "path",
            "source",
            "destination",
            "query",
            "root",
        ):
            value = request.arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return request.action

    def _confirm_action(
        self,
        request: ActionRequest,
        risk: ActionRisk,
    ) -> bool | None:
        subject = self._action_subject(request)
        preview = self._actions.confirmation_preview_for(request)
        preview_text = ""

        if preview is not None:
            if not preview.allowed:
                self._lyra(f"Prévia local bloqueou a ação:\n{preview.text}")
                return None
            preview_text = preview.text
            self._lyra(f"Prévia local da alteração:\n{preview_text}")

        self._lyra(
            f"Confirmação necessária para {request.action}: {subject} "
            f"({risk.value})."
        )
        dialog_text = (
            f"Autorizar esta ação?\n\n"
            f"{request.action}: {subject}\n"
            f"Risco: {risk.value}"
        )
        if preview_text:
            dialog_text += f"\n\nPrévia local:\n{preview_text}"

        choice = QMessageBox.question(
            self,
            "LYRA — confirmação necessária",
            dialog_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        approved = choice == QMessageBox.StandardButton.Yes
        if approved and preview is not None:
            request.arguments.update(preview.execution_guard)
        return approved

    def _start_action(self, request: ActionRequest) -> None:
        self._set_busy(True)
        worker = ActionWorker(self._actions, request)
        worker.signals.finished.connect(self._on_action_result)
        self._pool.start(worker)

    def _on_action_result(self, result: object) -> None:
        self._lyra(result.message, remember_in_session=True)
        self._set_busy(False)

    def _on_tool_progress(self, message: str) -> None:
        self._lyra(message, remember_in_session=True)

    def _on_tool_state(self, state: object) -> None:
        if not isinstance(state, LyraRunState):
            return
        self.workflow_status.setText(present_run_state(state).text)

    def _on_tool_loop_result(self, result: object) -> None:
        if not isinstance(result, ToolLoopResult):
            self._lyra("O loop de ferramentas retornou um resultado inválido.")
            self._finish_tool_task()
            return

        pending = result.pending_confirmation
        if pending is not None:
            decision = self._confirm_action(
                pending.request,
                pending.risk,
            )
            if decision is None:
                self._finish_tool_task()
                return
            self._resume_tool_loop(pending, approved=decision)
            return

        if result.final_reply is not None:
            self._lyra(result.final_reply, remember_in_session=True)

        if result.error is not None:
            self._lyra(result.error, remember_in_session=True)

        self._finish_tool_task()

    def _resume_tool_loop(
        self,
        pending: PendingActionConfirmation,
        *,
        approved: bool,
    ) -> None:
        control = self._active_control
        if control is None:
            self._lyra("Não há uma tarefa ativa para retomar.")
            self._finish_tool_task()
            return

        worker = ToolLoopResumeWorker(
            self._tool_loop,
            pending,
            control,
            approved=approved,
        )
        worker.signals.progress.connect(self._on_tool_progress)
        worker.signals.state.connect(self._on_tool_state)
        worker.signals.finished.connect(self._on_tool_loop_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _on_ai_failure(self, message: str) -> None:
        self._lyra(message)
        self._finish_tool_task()
