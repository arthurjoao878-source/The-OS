from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from theos.lyra.personality import (
    PersonalityContext,
    PersonalityFormality,
    PersonalityTone,
    PersonalityVerbosity,
)
from theos.lyra.planning import LyraPlanner, PlanKind
from theos.shell.assistant.context_status import present_context_status
from theos.shell.assistant.draft_recall import recallable_user_drafts
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
            personality=self._personality,
        )
        self._pool = QThreadPool.globalInstance()
        self._active_control: ExecutionControl | None = None

        self.setWindowTitle("LYRA — executor local: THE HANDS")
        self.resize(760, 600)

        root = QWidget()
        layout = QVBoxLayout(root)

        header = QLabel("LYRA  ● ON")
        self.workflow_status = QLabel("Tarefa: ociosa")
        self.context_status = QLabel()
        self.context_status.setObjectName("lyra_context_status")
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.transcript_focus_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+M"), self
        )
        self.transcript_focus_shortcut.setObjectName("lyra_transcript_focus_shortcut")
        self.transcript_focus_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._chat_base_font = QFont(self.chat.font())
        self.chat_follow = QCheckBox("Acompanhar novas mensagens")
        self.chat_follow.setObjectName("lyra_chat_follow")
        self.chat_follow.setToolTip(
            "Desmarque para manter a posicao de leitura durante novas respostas."
        )
        self.chat_follow.setChecked(True)
        self.chat_follow_toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+A"), self
        )
        self.chat_follow_toggle_shortcut.setObjectName(
            "lyra_chat_follow_toggle_shortcut"
        )
        self.chat_follow_toggle_shortcut.setContext(
            Qt.ShortcutContext.WindowShortcut
        )
        self.chat_text_size = QComboBox()
        self.chat_text_size.setObjectName("lyra_chat_text_size")
        self.chat_text_size_cycle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+T"), self
        )
        self.chat_text_size_cycle_shortcut.setObjectName(
            "lyra_chat_text_size_cycle_shortcut"
        )
        self.chat_text_size_cycle_shortcut.setContext(
            Qt.ShortcutContext.WindowShortcut
        )
        self.chat_text_size.setToolTip(
            "Altera somente a fonte do chat; nao altera o pedido enviado."
        )
        for label, size in (
            ("Sistema", None),
            ("Pequeno", 10),
            ("Normal", 12),
            ("Grande", 16),
        ):
            self.chat_text_size.addItem(label, size)
        self.chat_jump_start = QPushButton("Início")
        self.chat_jump_start.setObjectName("lyra_chat_jump_start")
        self.chat_jump_start.setToolTip("Ir ao início do chat sem alterar o acompanhamento.")
        self.chat_jump_end = QPushButton("Final")
        self.chat_jump_end.setObjectName("lyra_chat_jump_end")
        self.chat_jump_end.setToolTip("Ir ao final do chat sem alterar o acompanhamento.")
        self._last_find_query: str | None = None
        self.transcript_find = QLineEdit()
        self.transcript_find.setObjectName("lyra_transcript_find")
        self.transcript_find.setPlaceholderText("Localizar no chat...")
        self.transcript_find.setMaxLength(120)
        self.transcript_find_case_sensitive = QCheckBox("Diferenciar maiúsculas")
        self.transcript_find_case_sensitive.setObjectName(
            "lyra_transcript_find_case_sensitive"
        )
        self.transcript_find_case_sensitive.setToolTip(
            "Busca literal sensível a maiúsculas; padrão desativado."
        )
        self.transcript_find_whole_word = QCheckBox("Palavra inteira")
        self.transcript_find_whole_word.setObjectName(
            "lyra_transcript_find_whole_word"
        )
        self.transcript_find_whole_word_toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+W"), self
        )
        self.transcript_find_whole_word_toggle_shortcut.setObjectName(
            "lyra_transcript_find_whole_word_toggle_shortcut"
        )
        self.transcript_find_whole_word_toggle_shortcut.setContext(
            Qt.ShortcutContext.WindowShortcut
        )
        self.transcript_find_whole_word.setToolTip(
            "Busca palavras completas; padrao desativado."
        )
        self.transcript_find_focus_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.transcript_find_focus_shortcut.setObjectName(
            "lyra_transcript_find_focus_shortcut"
        )
        self.transcript_find_next_shortcut = QShortcut(QKeySequence("F3"), self)
        self.transcript_find_next_shortcut.setObjectName(
            "lyra_transcript_find_next_shortcut"
        )
        self.transcript_find_previous_shortcut = QShortcut(
            QKeySequence("Shift+F3"), self
        )
        self.transcript_find_previous_shortcut.setObjectName(
            "lyra_transcript_find_previous_shortcut"
        )
        self.transcript_find_clear = QPushButton("Limpar busca")
        self.transcript_find_clear.setObjectName("lyra_transcript_find_clear")
        self.transcript_find_clear.setToolTip(
            "Limpa somente a consulta e os indicadores, sem alterar os modos."
        )
        self.transcript_find_escape_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Escape), self.transcript_find
        )
        self.transcript_find_escape_shortcut.setObjectName(
            "lyra_transcript_find_escape_shortcut"
        )
        self.transcript_find_escape_shortcut.setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        self.transcript_find_enter_next_shortcut = QShortcut(
            QKeySequence("Return"), self.transcript_find
        )
        self.transcript_find_enter_next_shortcut.setObjectName(
            "lyra_transcript_find_enter_next_shortcut"
        )
        self.transcript_find_enter_next_shortcut.setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        self.transcript_find_enter_previous_shortcut = QShortcut(
            QKeySequence("Shift+Return"), self.transcript_find
        )
        self.transcript_find_enter_previous_shortcut.setObjectName(
            "lyra_transcript_find_enter_previous_shortcut"
        )
        self.transcript_find_enter_previous_shortcut.setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        self.transcript_find_keypad_enter_next_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Enter), self.transcript_find
        )
        self.transcript_find_keypad_enter_next_shortcut.setObjectName(
            "lyra_transcript_find_keypad_enter_next_shortcut"
        )
        self.transcript_find_keypad_enter_next_shortcut.setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        self.transcript_find_keypad_enter_previous_shortcut = QShortcut(
            QKeySequence("Shift+Enter"), self.transcript_find
        )
        self.transcript_find_keypad_enter_previous_shortcut.setObjectName(
            "lyra_transcript_find_keypad_enter_previous_shortcut"
        )
        self.transcript_find_keypad_enter_previous_shortcut.setContext(
            Qt.ShortcutContext.WidgetShortcut
        )
        self.transcript_find_next = QPushButton("Próximo")
        self.transcript_find_next.setObjectName("lyra_transcript_find_next")
        self.transcript_find_previous = QPushButton("Anterior")
        self.transcript_find_previous.setObjectName("lyra_transcript_find_previous")
        self.transcript_find_status = QLabel("Busca: pronta")
        self.transcript_find_status.setObjectName("lyra_transcript_find_status")
        self.transcript_match_count = QLabel("Ocorrências: —")
        self.transcript_match_count.setObjectName("lyra_transcript_match_count")
        self.transcript_match_position = QLabel("Posição: —")
        self.transcript_match_position.setObjectName("lyra_transcript_match_position")
        self.transcript_match_position.setToolTip(
            "Posicao da correspondencia selecionada; no maximo 256 resultados exatos."
        )
        self.transcript_match_count.setToolTip(
            "Contagem literal limitada a 256 correspondencias no chat visivel."
        )
        self.input = QLineEdit()
        self.input.setPlaceholderText("Diga algo...")
        self.input.setMaxLength(4096)
        self.composer_focus_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.composer_focus_shortcut.setObjectName("lyra_composer_focus_shortcut")
        self.composer_focus_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.composer_length_status = QLabel("Mensagem: 0/4096")
        self.composer_length_status.setObjectName("lyra_composer_length_status")
        self.composer_length_status.setToolTip(
            "O campo aceita ate 4096 caracteres; mostra apenas a contagem."
        )
        self._draft_recall_index: int | None = None
        self._draft_recall_original = ""
        self._draft_recall_items: tuple[str, ...] = ()
        self.draft_previous = QPushButton("Pedido anterior")
        self.draft_previous.setObjectName("lyra_draft_previous")
        self.draft_next = QPushButton("Pedido seguinte")
        self.draft_next.setObjectName("lyra_draft_next")
        self.send = QPushButton("Enviar")

        self.pause_task = QPushButton("Pausar")
        self.resume_task = QPushButton("Retomar")
        self.cancel_task = QPushButton("Cancelar")
        self.session_reset = QPushButton("Nova conversa")
        self.session_reset.setObjectName("lyra_session_reset")
        self.session_reset.setToolTip(
            "Limpa somente o histórico temporário da sessão e percepção."
        )

        self.personality_tone = QComboBox()
        self.personality_tone.setObjectName("lyra_personality_tone")
        for label, value in (
            ("Natural", PersonalityTone.NATURAL),
            ("Acolhedor", PersonalityTone.WARM),
            ("Calmo", PersonalityTone.CALM),
            ("Descontraído", PersonalityTone.PLAYFUL),
        ):
            self.personality_tone.addItem(label, value.value)

        self.personality_verbosity = QComboBox()
        self.personality_verbosity.setObjectName("lyra_personality_verbosity")
        for label, value in (
            ("Conciso", PersonalityVerbosity.CONCISE),
            ("Equilibrado", PersonalityVerbosity.BALANCED),
            ("Detalhado", PersonalityVerbosity.DETAILED),
        ):
            self.personality_verbosity.addItem(label, value.value)

        self.personality_formality = QComboBox()
        self.personality_formality.setObjectName("lyra_personality_formality")
        for label, value in (
            ("Casual", PersonalityFormality.CASUAL),
            ("Equilibrado", PersonalityFormality.BALANCED),
            ("Formal", PersonalityFormality.FORMAL),
        ):
            self.personality_formality.addItem(label, value.value)

        self.personality_reset = QPushButton("Restaurar estilo")
        self.personality_reset.setObjectName("lyra_personality_reset")
        self.personality_reset.setToolTip(
            "Estilo de resposta local; não altera ferramentas nem permissões."
        )
        personality_controls = QHBoxLayout()
        personality_controls.addWidget(QLabel("Tom"))
        personality_controls.addWidget(self.personality_tone)
        personality_controls.addWidget(QLabel("Detalhe"))
        personality_controls.addWidget(self.personality_verbosity)
        personality_controls.addWidget(QLabel("Formalidade"))
        personality_controls.addWidget(self.personality_formality)
        personality_controls.addWidget(self.personality_reset)
        self._sync_personality_controls()

        find_controls = QHBoxLayout()
        find_controls.addWidget(self.transcript_find, 1)
        find_controls.addWidget(self.transcript_find_clear)
        find_controls.addWidget(self.transcript_find_previous)
        find_controls.addWidget(self.transcript_find_next)
        find_controls.addWidget(self.transcript_find_status)
        find_controls.addWidget(self.transcript_match_count)
        find_controls.addWidget(self.transcript_match_position)

        chat_presentation_controls = QHBoxLayout()
        chat_presentation_controls.addWidget(self.chat_follow)
        chat_presentation_controls.addWidget(self.chat_jump_start)
        chat_presentation_controls.addWidget(self.chat_jump_end)
        chat_presentation_controls.addStretch(1)
        chat_presentation_controls.addWidget(QLabel("Tamanho do texto"))
        chat_presentation_controls.addWidget(self.chat_text_size)

        composer = QHBoxLayout()
        composer.addWidget(self.draft_previous)
        composer.addWidget(self.draft_next)
        composer.addWidget(self.input, 1)
        composer.addWidget(self.composer_length_status)
        composer.addWidget(self.send)

        controls = QHBoxLayout()
        controls.addWidget(self.pause_task)
        controls.addWidget(self.resume_task)
        controls.addWidget(self.cancel_task)
        controls.addWidget(self.session_reset)
        controls.addStretch(1)

        layout.addWidget(header)
        layout.addLayout(personality_controls)
        layout.addWidget(self.workflow_status)
        layout.addWidget(self.context_status)
        layout.addWidget(self.chat, 1)
        layout.addLayout(chat_presentation_controls)
        layout.addLayout(find_controls)
        layout.addWidget(self.transcript_find_case_sensitive)
        layout.addWidget(self.transcript_find_whole_word)
        layout.addLayout(composer)
        layout.addLayout(controls)

        self.setCentralWidget(root)

        self.send.clicked.connect(self._submit)
        self.input.returnPressed.connect(self._submit)
        self.composer_focus_shortcut.activated.connect(self._focus_composer)
        self.transcript_focus_shortcut.activated.connect(self._focus_transcript)
        self.input.textChanged.connect(self._on_composer_text_changed)
        self.input.textEdited.connect(self._clear_draft_recall_navigation)
        self.draft_previous.clicked.connect(self._recall_previous_draft)
        self.draft_next.clicked.connect(self._recall_next_draft)
        self.pause_task.clicked.connect(self._pause_active_task)
        self.resume_task.clicked.connect(self._resume_active_task)
        self.cancel_task.clicked.connect(self._cancel_active_task)
        self.session_reset.clicked.connect(self._reset_session_context)
        self.chat_follow.toggled.connect(self._on_chat_follow_toggled)
        self.chat_follow_toggle_shortcut.activated.connect(
            self._toggle_chat_follow_shortcut
        )
        self.chat_jump_start.clicked.connect(self._jump_to_chat_start)
        self.chat_jump_end.clicked.connect(self._jump_to_chat_end)
        self.chat_text_size.currentIndexChanged.connect(self._apply_chat_text_size)
        self.chat_text_size_cycle_shortcut.activated.connect(
            self._cycle_chat_text_size_shortcut
        )
        self.transcript_find.textChanged.connect(self._on_transcript_find_query_changed)
        self.transcript_find_clear.clicked.connect(self._clear_transcript_find)
        self.transcript_find_escape_shortcut.activated.connect(
            self._leave_transcript_find
        )
        self.transcript_find_enter_next_shortcut.activated.connect(
            self._find_next_in_transcript
        )
        self.transcript_find_enter_previous_shortcut.activated.connect(
            self._find_previous_in_transcript
        )
        self.transcript_find_keypad_enter_next_shortcut.activated.connect(
            self._find_next_in_transcript
        )
        self.transcript_find_keypad_enter_previous_shortcut.activated.connect(
            self._find_previous_in_transcript
        )
        self.transcript_find_case_sensitive.toggled.connect(
            self._on_transcript_find_mode_changed
        )
        self.transcript_find_whole_word.toggled.connect(
            self._on_transcript_find_mode_changed
        )
        self.transcript_find_whole_word_toggle_shortcut.activated.connect(
            self._toggle_transcript_find_whole_word_shortcut
        )
        self.transcript_find_focus_shortcut.activated.connect(
            self._focus_transcript_find
        )
        self.transcript_find_next_shortcut.activated.connect(
            self._find_next_in_transcript
        )
        self.transcript_find_previous_shortcut.activated.connect(
            self._find_previous_in_transcript
        )
        self.transcript_find_next.clicked.connect(self._find_next_in_transcript)
        self.transcript_find_previous.clicked.connect(self._find_previous_in_transcript)
        self.personality_tone.currentIndexChanged.connect(
            self._on_personality_controls_changed
        )
        self.personality_verbosity.currentIndexChanged.connect(
            self._on_personality_controls_changed
        )
        self.personality_formality.currentIndexChanged.connect(
            self._on_personality_controls_changed
        )
        self.personality_reset.clicked.connect(self._reset_personality_controls)

        self._update_task_controls(None)
        self._refresh_context_status()
        self._lyra("Pronta.")

    def _refresh_context_status(self) -> None:
        self.context_status.setText(
            present_context_status(self._context, self._perception)
        )

    def _cycle_chat_text_size_shortcut(self) -> None:
        if (
            not self.chat_text_size.isEnabled()
            or not self.chat_text_size_cycle_shortcut.isEnabled()
            or self.chat_text_size.count() != 4
            or tuple(self.chat_text_size.itemData(i) for i in range(4))
            != (None, 10, 12, 16)
        ):
            return
        index = self.chat_text_size.currentIndex()
        if index not in (0, 1, 2, 3):
            return
        self.chat_text_size.setCurrentIndex((index + 1) % 4)

    def _apply_chat_text_size(self, _index: int) -> None:
        size = self.chat_text_size.currentData()
        if size is not None and (type(size) is not int or size not in (10, 12, 16)):
            return
        font = QFont(self._chat_base_font)
        if size is not None:
            font.setPointSize(size)
        self.chat.setFont(font)

    def _on_composer_text_changed(self, _text: str) -> None:
        self.composer_length_status.setText(
            f"Mensagem: {len(self.input.text())}/4096"
        )

    def _on_transcript_find_query_changed(self, _text: str) -> None:
        self.transcript_match_count.setText("Ocorrências: —")
        self.transcript_match_position.setText("Posição: —")
        self._last_find_query = None
        self.transcript_find_status.setText("Busca: pronta")

    def _toggle_transcript_find_whole_word_shortcut(self) -> None:
        if (
            not self.transcript_find.isEnabled()
            or not self.transcript_find_whole_word.isEnabled()
            or not self.transcript_find_whole_word_toggle_shortcut.isEnabled()
        ):
            return
        self.transcript_find_whole_word.setChecked(
            not self.transcript_find_whole_word.isChecked()
        )

    def _on_transcript_find_mode_changed(self, _checked: bool) -> None:
        self._on_transcript_find_query_changed("")

    def _clear_transcript_find(self) -> None:
        if (
            not self.transcript_find.isEnabled()
            or not self.transcript_find_clear.isEnabled()
        ):
            return
        if self.transcript_find.text():
            self.transcript_find.clear()
        else:
            self._on_transcript_find_query_changed("")

    def _leave_transcript_find(self) -> None:
        if (
            not self.transcript_find.isEnabled()
            or not self.input.isEnabled()
            or not self.transcript_find.hasFocus()
        ):
            return
        self.input.setFocus()

    def _focus_transcript(self) -> None:
        if not self.chat.isEnabled() or not self.transcript_focus_shortcut.isEnabled():
            return
        self.chat.setFocus()

    def _focus_composer(self) -> None:
        if not self.input.isEnabled():
            return
        self.input.setFocus()

    def _focus_transcript_find(self) -> None:
        if not self.transcript_find.isEnabled():
            return
        self.transcript_find.setFocus()

    def _find_next_in_transcript(self) -> None:
        self._find_in_transcript(backward=False)

    def _find_previous_in_transcript(self) -> None:
        self._find_in_transcript(backward=True)

    def _find_in_transcript(self, *, backward: bool) -> None:
        if not self.transcript_find.isEnabled():
            return
        query = self.transcript_find.text().strip()
        if not query:
            self.transcript_match_count.setText("Ocorrências: —")
            self.transcript_match_position.setText("Posição: —")
            self.transcript_find_status.setText("Busca: informe termo")
            return
        if len(query) > 120:
            self.transcript_match_count.setText("Ocorrências: indisponível")
            self.transcript_match_position.setText("Posição: indisponível")
            self.transcript_find_status.setText("Busca: termo acima do limite")
            return
        if len(self.chat.toPlainText()) > 65536:
            self.transcript_match_count.setText("Ocorrências: indisponível")
            self.transcript_match_position.setText("Posição: indisponível")
            self.transcript_find_status.setText("Busca: conversa acima do limite")
            return
        direction = (
            QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
        )
        if query != self._last_find_query:
            self.chat.moveCursor(direction)
        flags = QTextDocument.FindFlag(0)
        if self.transcript_find_case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.transcript_find_whole_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        found = self.chat.find(query, flags)
        if not found:
            self.chat.moveCursor(direction)
            found = self.chat.find(query, flags)
        self._last_find_query = query
        self._update_transcript_match_count(
            query,
            self.chat.textCursor().selectionStart() if found else None,
        )
        self.transcript_find_status.setText(
            "Busca: resultado selecionado" if found else "Busca: nenhum resultado"
        )

    def _update_transcript_match_count(
        self, query: str, selected_start: int | None = None
    ) -> None:
        document = self.chat.document()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        matches = 0
        rank: int | None = None
        flags = QTextDocument.FindFlag(0)
        if self.transcript_find_case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.transcript_find_whole_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        while matches <= 256:
            cursor = document.find(query, cursor, flags)
            if cursor.isNull():
                self.transcript_match_count.setText(f"Ocorrências: {matches}")
                if rank is None:
                    self.transcript_match_position.setText("Posição: —")
                else:
                    self.transcript_match_position.setText(
                        f"Posição: {rank} de {matches}"
                    )
                return
            matches += 1
            if selected_start is not None and cursor.selectionStart() == selected_start:
                rank = matches
        self.transcript_match_count.setText("Ocorrências: 256+")
        if rank is not None and rank <= 256:
            self.transcript_match_position.setText(f"Posição: {rank} de 256+")
        elif selected_start is not None:
            self.transcript_match_position.setText("Posição: >256 de 256+")
        else:
            self.transcript_match_position.setText("Posição: —")

    def _clear_draft_recall_navigation(self, _text: str = "") -> None:
        self._draft_recall_index = None
        self._draft_recall_original = ""
        self._draft_recall_items = ()

    def _recall_previous_draft(self) -> None:
        self._browse_draft_history(older=True)

    def _recall_next_draft(self) -> None:
        self._browse_draft_history(older=False)

    def _browse_draft_history(self, *, older: bool) -> None:
        if not self.input.isEnabled():
            return
        current = self._draft_recall_index
        if older:
            if current is None:
                items = recallable_user_drafts(self._context)
                if not items:
                    return
                self._draft_recall_items = items
                self._draft_recall_original = self.input.text()
                current = len(items) - 1
            elif current > 0:
                current -= 1
            else:
                return
            self._draft_recall_index = current
            self.input.setText(self._draft_recall_items[current])
            return
        if current is None:
            return
        if current < len(self._draft_recall_items) - 1:
            current += 1
            self._draft_recall_index = current
            self.input.setText(self._draft_recall_items[current])
            return
        original = self._draft_recall_original
        self._clear_draft_recall_navigation()
        self.input.setText(original)

    def _jump_to_chat_start(self) -> None:
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.minimum())

    def _jump_to_chat_end(self) -> None:
        scrollbar = self.chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _toggle_chat_follow_shortcut(self) -> None:
        if (
            not self.chat_follow.isEnabled()
            or not self.chat_follow_toggle_shortcut.isEnabled()
        ):
            return
        self.chat_follow.setChecked(not self.chat_follow.isChecked())

    def _on_chat_follow_toggled(self, enabled: bool) -> None:
        if enabled:
            scrollbar = self.chat.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _append_chat(self, speaker: str, text: str) -> None:
        scrollbar = self.chat.verticalScrollBar()
        frozen_position = (
            None if self.chat_follow.isChecked() else scrollbar.value()
        )
        self.chat.appendPlainText(f"{speaker}\n{text}\n")
        if frozen_position is None:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(min(frozen_position, scrollbar.maximum()))

    def _you(self, text: str) -> None:
        self._append_chat("Você", text)

    def _lyra(self, text: str, *, remember_in_session: bool = False) -> None:
        self._append_chat("LYRA", text)
        if remember_in_session:
            self._context.add_assistant(text)
            self._refresh_context_status()

    def _set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.composer_focus_shortcut.setEnabled(not busy)
        self.transcript_focus_shortcut.setEnabled(not busy)
        self.chat_follow_toggle_shortcut.setEnabled(not busy)
        self.chat_text_size_cycle_shortcut.setEnabled(not busy)
        self.send.setEnabled(not busy)
        self.session_reset.setEnabled(not busy)
        self.transcript_find.setEnabled(not busy)
        self.transcript_find_clear.setEnabled(not busy)
        self.transcript_find_escape_shortcut.setEnabled(not busy)
        self.transcript_find_enter_next_shortcut.setEnabled(not busy)
        self.transcript_find_enter_previous_shortcut.setEnabled(not busy)
        self.transcript_find_keypad_enter_next_shortcut.setEnabled(not busy)
        self.transcript_find_keypad_enter_previous_shortcut.setEnabled(not busy)
        self.transcript_find_case_sensitive.setEnabled(not busy)
        self.transcript_find_whole_word.setEnabled(not busy)
        self.transcript_find_whole_word_toggle_shortcut.setEnabled(not busy)
        self.transcript_find_focus_shortcut.setEnabled(not busy)
        self.transcript_find_next_shortcut.setEnabled(not busy)
        self.transcript_find_previous_shortcut.setEnabled(not busy)
        self.transcript_find_next.setEnabled(not busy)
        self.transcript_find_previous.setEnabled(not busy)
        self.draft_previous.setEnabled(not busy)
        self.draft_next.setEnabled(not busy)
        self.personality_tone.setEnabled(not busy)
        self.personality_verbosity.setEnabled(not busy)
        self.personality_formality.setEnabled(not busy)
        self.personality_reset.setEnabled(not busy)
        if not busy:
            self.input.setFocus()

    def _sync_personality_controls(self) -> None:
        snapshot = self._personality.snapshot()
        for control, value in (
            (self.personality_tone, snapshot.tone.value),
            (self.personality_verbosity, snapshot.verbosity.value),
            (self.personality_formality, snapshot.formality.value),
        ):
            index = control.findData(value)
            if index < 0:
                raise RuntimeError("personality control lacks a required finite value")
            was_blocked = control.blockSignals(True)
            try:
                control.setCurrentIndex(index)
            finally:
                control.blockSignals(was_blocked)

    def _on_personality_controls_changed(self, _index: int) -> None:
        try:
            tone = PersonalityTone(self.personality_tone.currentData())
            verbosity = PersonalityVerbosity(self.personality_verbosity.currentData())
            formality = PersonalityFormality(self.personality_formality.currentData())
        except (TypeError, ValueError):
            self._sync_personality_controls()
            return
        self._personality.update(
            tone=tone,
            verbosity=verbosity,
            formality=formality,
        )

    def _reset_personality_controls(self) -> None:
        self._personality.reset()
        self._sync_personality_controls()

    def _reset_session_context(self) -> None:
        if not self.session_reset.isEnabled():
            return
        choice = QMessageBox.question(
            self,
            "LYRA — nova conversa",
            "Iniciar uma nova conversa?\n\n"
            "Isso limpa o chat e o contexto temporário da sessão e percepção. "
            "Memórias salvas e preferências de estilo serão preservadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self._context.clear()
        self._perception.clear()
        self.chat.clear()
        self.chat_follow.setChecked(True)
        self.chat_text_size.setCurrentIndex(0)
        self._clear_draft_recall_navigation()
        self.transcript_find_case_sensitive.setChecked(False)
        self.transcript_find_whole_word.setChecked(False)
        self.transcript_find.clear()
        self._on_transcript_find_query_changed("")
        self.input.clear()
        self.workflow_status.setText("Tarefa: ociosa")
        self._lyra("Nova conversa iniciada.")
        self._refresh_context_status()

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
        if not self.input.isEnabled():
            return
        text = self.input.text().strip()
        if not text or len(text) > 4096:
            return

        history = self._context.provider_snapshot()
        self._context.add_user(text)
        self._clear_draft_recall_navigation()
        self._refresh_context_status()
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
        self._refresh_context_status()

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
