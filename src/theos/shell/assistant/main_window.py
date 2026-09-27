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
from theos.lyra.conversation.smoke_intent import resolve_smoke_intent
from theos.lyra.memory.intent import MemoryIntentKind, resolve_memory_intent
from theos.lyra.memory.service import MemoryService


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
    def __init__(self, provider: AIProvider, text: str) -> None:
        super().__init__()
        self.provider = provider
        self.text = text
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            reply = self.provider.reply(self.text)
        except AIProviderError as exception:
            self.signals.failed.emit(str(exception))
            return
        except (TypeError, ValueError):
            self.signals.failed.emit("O provedor de IA retornou uma resposta invÃ¡lida.")
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
        send = QPushButton("Enviar")

        composer = QHBoxLayout()
        composer.addWidget(self.input, 1)
        composer.addWidget(send)

        layout.addWidget(header)
        layout.addWidget(self.chat, 1)
        layout.addLayout(composer)

        self.setCentralWidget(root)

        send.clicked.connect(self._submit)
        self.input.returnPressed.connect(self._submit)

        self._lyra("Pronta.")

    def _you(self, text: str) -> None:
        self.chat.appendPlainText(f"Você\n{text}\n")

    def _lyra(self, text: str) -> None:
        self.chat.appendPlainText(f"LYRA\n{text}\n")

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return

        self.input.clear()
        self._you(text)

        memory_intent = resolve_memory_intent(text)
        if memory_intent is not None:
            if memory_intent.kind is MemoryIntentKind.REMEMBER:
                self._memory.remember(memory_intent.text)
                self._lyra("Memória salva.")
                return

            results = self._memory.recall(memory_intent.text, limit=3)
            if not results:
                self._lyra("Não encontrei nada na memória sobre isso.")
                return
            remembered = "\n".join(
                f"• {record.content}"
                for record in results
                if record.content is not None
            )
            self._lyra(f"Eu lembro:\n{remembered}")
            return

        request = resolve_smoke_intent(text)
        if request is not None:
            app = str(request.arguments.get("application", "aplicativo"))
            self._lyra(f"Abrindo {app}...")

            worker = ActionWorker(self._actions, request)
            worker.signals.finished.connect(self._on_action_result)
            self._pool.start(worker)
            return

        self._lyra("Pensando...")
        worker = AIWorker(self._ai, text)
        worker.signals.finished.connect(self._on_ai_result)
        worker.signals.failed.connect(self._on_ai_failure)
        self._pool.start(worker)

    def _on_action_result(self, result: object) -> None:
        self._lyra(result.message)

    def _on_ai_result(self, reply: object) -> None:
        self._lyra(reply.text)

    def _on_ai_failure(self, message: str) -> None:
        self._lyra(message)
