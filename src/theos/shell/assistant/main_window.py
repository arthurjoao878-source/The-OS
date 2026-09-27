from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from theos.core.actions.registry import ActionRegistry
from theos.integrations.ai import AIProvider, AIProviderError
from theos.lyra.context import ConversationTurn, SessionContext
from theos.lyra.memory.intent import MemoryIntentKind
from theos.lyra.memory.service import MemoryService
from theos.lyra.planning import LyraPlanner, PlanKind


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ActionWorker(QRunnable):
    def __init__(self, action_registry: ActionRegistry, request: object) -> None:
        super().__init__()
        self.action_registry = action_registry
        self.request = request
        self.signals = WorkerSignals()

    def run(self) -> None:
        result = self.action_registry.execute(self.request)
        self.signals.finished.emit(result)


class AIWorker(QRunnable):
    def __init__(
        self,
        provider: AIProvider,
        text: str,
        history: tuple[ConversationTurn, ...],
    ) -> None:
        super().__init__()
        self.provider = provider
        self.text = text
        self.history = history
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            reply = self.provider.reply(self.text, history=self.history)
        except AIProviderError as exception:
            self.signals.failed.emit(str(exception))
            return
        except (TypeError, ValueError):
            self.signals.failed.emit("O provedor de IA retornou uma resposta inválida.")
            return
        self.signals.finished.emit(reply)


class MainWindow(QMainWindow):
    def __init__(
        self,
        action_registry: ActionRegistry,
        memory_service: MemoryService,
        ai_provider: AIProvider,
    ) -> None:
        super().__init__()
        self._actions = action_registry
        self._memory = memory_service
        self._ai = ai_provider
        self._planner = LyraPlanner()
        self._context = SessionContext(max_turns=12)
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

            app = str(request.arguments.get("application", "aplicativo"))
            self._lyra(f"Abrindo {app}...")
            self._set_busy(True)

            worker = ActionWorker(self._actions, request)
            worker.signals.finished.connect(self._on_action_result)
            self._pool.start(worker)
            return

        self._lyra("Pensando...")
        self._set_busy(True)
        worker = AIWorker(self._ai, text, history)
        worker.signals.finished.connect(self._on_ai_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _on_action_result(self, result: object) -> None:
        self._lyra(result.message, remember_in_session=True)
        self._set_busy(False)

    def _on_ai_result(self, reply: object) -> None:
        self._lyra(reply.text, remember_in_session=True)
        self._set_busy(False)

    def _on_ai_failure(self, message: str) -> None:
        self._lyra(message)
        self._set_busy(False)
