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
    PendingActionConfirmation,
    ToolLoopExecutor,
    ToolLoopResult,
)
from theos.lyra.memory.intent import MemoryIntentKind
from theos.lyra.memory.service import MemoryService
from theos.lyra.planning import LyraPlanner, PlanKind


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


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
    ) -> None:
        super().__init__()
        self.executor = executor
        self.text = text
        self.history = history
        self.tools = tools
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.executor.execute(
                self.text,
                history=self.history,
                tools=self.tools,
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
        *,
        approved: bool,
    ) -> None:
        super().__init__()
        self.executor = executor
        self.pending = pending
        self.approved = approved
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.executor.resume(
                self.pending,
                approved=self.approved,
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
        self._tool_loop = ToolLoopExecutor(
            ai_provider,
            action_registry,
            tool_catalog,
        )
        self._pool = QThreadPool.globalInstance()

        self.setWindowTitle("THE OS — LYRA")
        self.resize(760, 560)

        root = QWidget()
        layout = QVBoxLayout(root)

        header = QLabel("LYRA  ● ON")
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Diga algo...")
        self.send = QPushButton("Enviar")

        composer = QHBoxLayout()
        composer.addWidget(self.input, 1)
        composer.addWidget(self.send)

        layout.addWidget(header)
        layout.addWidget(self.chat, 1)
        layout.addLayout(composer)

        self.setCentralWidget(root)

        self.send.clicked.connect(self._submit)
        self.input.returnPressed.connect(self._submit)

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

        self._lyra("Pensando...")
        self._set_busy(True)
        worker = ToolLoopWorker(
            self._tool_loop,
            text,
            history,
            self._available_ai_tools(),
        )
        worker.signals.finished.connect(self._on_tool_loop_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _handle_direct_action(self, request: ActionRequest) -> None:
        risk = self._actions.risk_for(request)
        if requires_confirmation(risk) and not self._confirm_action(request, risk):
            self._lyra("Ação cancelada.", remember_in_session=True)
            return

        app = str(request.arguments.get("application", "aplicativo"))
        self._lyra(f"Abrindo {app}...")
        self._start_action(request)

    def _confirm_action(
        self,
        request: ActionRequest,
        risk: ActionRisk,
    ) -> bool:
        app = str(request.arguments.get("application", request.action))
        self._lyra(
            f"Confirmação necessária para {request.action}: {app} "
            f"({risk.value})."
        )
        choice = QMessageBox.question(
            self,
            "LYRA — confirmação necessária",
            f"Autorizar esta ação?\n\n{request.action}: {app}\nRisco: {risk.value}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def _start_action(self, request: ActionRequest) -> None:
        self._set_busy(True)
        worker = ActionWorker(self._actions, request)
        worker.signals.finished.connect(self._on_action_result)
        self._pool.start(worker)

    def _on_action_result(self, result: object) -> None:
        self._lyra(result.message, remember_in_session=True)
        self._set_busy(False)

    def _on_tool_loop_result(self, result: object) -> None:
        if not isinstance(result, ToolLoopResult):
            self._lyra("O loop de ferramentas retornou um resultado inválido.")
            self._set_busy(False)
            return

        for message in result.messages:
            self._lyra(message, remember_in_session=True)

        pending = result.pending_confirmation
        if pending is not None:
            approved = self._confirm_action(
                pending.request,
                pending.risk,
            )
            self._resume_tool_loop(pending, approved=approved)
            return

        if result.final_reply is not None:
            self._lyra(result.final_reply, remember_in_session=True)

        if result.error is not None:
            self._lyra(result.error, remember_in_session=True)

        self._set_busy(False)

    def _resume_tool_loop(
        self,
        pending: PendingActionConfirmation,
        *,
        approved: bool,
    ) -> None:
        worker = ToolLoopResumeWorker(
            self._tool_loop,
            pending,
            approved=approved,
        )
        worker.signals.finished.connect(self._on_tool_loop_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _on_ai_failure(self, message: str) -> None:
        self._lyra(message)
        self._set_busy(False)
