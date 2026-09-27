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
from theos.lyra.conversation.smoke_intent import resolve_smoke_intent


class WorkerSignals(QObject):
    finished = Signal(object)


class ActionWorker(QRunnable):
    def __init__(self, action_registry: ActionRegistry, request: object) -> None:
        super().__init__()
        self.action_registry = action_registry
        self.request = request
        self.signals = WorkerSignals()

    def run(self) -> None:
        result = self.action_registry.execute(self.request)
        self.signals.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self, action_registry: ActionRegistry) -> None:
        super().__init__()
        self._actions = action_registry
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

        self._lyra("Pronta. O primeiro teste é: abre o Discord.")

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

        request = resolve_smoke_intent(text)
        if request is None:
            self._lyra("Ainda estou no primeiro slice. Tente: abre o Discord.")
            return

        app = str(request.arguments.get("application", "aplicativo"))
        self._lyra(f"Abrindo {app}...")

        worker = ActionWorker(self._actions, request)
        worker.signals.finished.connect(self._on_result)
        self._pool.start(worker)

    def _on_result(self, result: object) -> None:
        self._lyra(result.message)