from __future__ import annotations

import hashlib

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.window_keys import (
    is_allowed_window_key,
    is_destructive_window_key,
)
from theos.core.window_shortcuts import (
    is_allowed_window_shortcut,
    is_destructive_window_shortcut,
    is_privileged_window_shortcut,
)
from theos.core.window_targets import (
    is_window_target_token,
    normalize_window_query,
)
from theos.integrations.windows.desktop_windows import WindowsDesktopWindowAdapter


class WindowSnapshotAction:
    name = "window_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        raw_query = request.arguments.get("query")
        normalized_query = (
            None
            if raw_query is None
            else normalize_window_query(raw_query)
        )
        if raw_query is not None and normalized_query is None:
            return ConfirmationPreview(
                allowed=False,
                text="Inspeção de janelas bloqueada: filtro local inválido.",
            )

        filter_text = (
            "Sem filtro local: serão retornadas até as 12 primeiras janelas visíveis "
            "na ordem Z."
            if normalized_query is None
            else (
                f"Filtro local solicitado: {normalized_query}\n"
                "Após a confirmação, todas as janelas visíveis com título serão "
                "enumeradas localmente, mas somente correspondências determinísticas "
                "desse texto no título limitado ou nome do processo poderão ser "
                "retornadas, até o limite de 12."
            )
        )
        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR JANELAS VISÍVEIS\n"
                "A LYRA enumerará localmente janelas de nível superior que estão visíveis "
                "e enviará ao provedor de IA somente título da janela, nome do processo, "
                "PID e um token opaco de alvo gerado localmente.\n"
                f"{filter_text}\n"
                "Limite de saída: 12 janelas; títulos são limitados a 160 caracteres.\n"
                "Não serão coletados conteúdo interno das janelas, teclas digitadas, "
                "capturas de tela, caminhos de executáveis, handles brutos ou títulos "
                "de janelas ocultas."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_query = request.arguments.get("query")
        normalized_query = (
            None
            if raw_query is None
            else normalize_window_query(raw_query)
        )
        if raw_query is not None and normalized_query is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O filtro local de janelas é inválido.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = (
                self._windows.snapshot()
                if normalized_query is None
                else self._windows.snapshot(normalized_query)
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "WINDOW_QUERY_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O filtro local de janelas é inválido.",
                    evidence={"reason": reason},
                    error_code="ACTION_VALIDATION_FAILED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar as janelas visíveis.",
                evidence={"reason": reason},
                error_code="WINDOW_SNAPSHOT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar as janelas visíveis.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_SNAPSHOT_FAILED",
            )

        observed = int(evidence["observed_windows"])
        returned = int(evidence["returned_windows"])
        if bool(evidence.get("filter_applied")):
            matched = int(evidence["matched_windows"])
            message = (
                f"Janelas inspecionadas: {observed} visíveis com título; "
                f"{matched} corresponderam ao filtro local; {returned} retornadas."
            )
        else:
            message = (
                f"Janelas inspecionadas: {observed} visíveis com título; "
                f"{returned} retornadas."
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=message,
            evidence=evidence,
        )


class ActivateWindowAction:
    name = "activate_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="PID, título e token opaco exatos da janela são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.activate_window(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a ativação foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_FOREGROUND_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou essa janela em primeiro plano.",
                    evidence={"reason": reason},
                    error_code="WINDOW_ACTIVATION_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ativar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_ACTIVATION_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui ativar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_ACTIVATION_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela ativada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']})."
            ),
            evidence=evidence,
        )


_EXPECTED_KEY_PID = "_theos_expected_key_pid"
_EXPECTED_KEY_TITLE = "_theos_expected_key_title"
_EXPECTED_KEY_TARGET_TOKEN = "_theos_expected_key_target_token"
_EXPECTED_KEY_NAME = "_theos_expected_key_name"
_EXPECTED_SHORTCUT_PID = "_theos_expected_shortcut_pid"
_EXPECTED_SHORTCUT_TITLE = "_theos_expected_shortcut_title"
_EXPECTED_SHORTCUT_TARGET_TOKEN = "_theos_expected_shortcut_target_token"
_EXPECTED_SHORTCUT_NAME = "_theos_expected_shortcut_name"
_EXPECTED_TEXT_PID = "_theos_expected_text_pid"
_EXPECTED_TEXT_TITLE = "_theos_expected_text_title"
_EXPECTED_TEXT_TARGET_TOKEN = "_theos_expected_text_target_token"
_EXPECTED_TEXT_SHA256 = "_theos_expected_text_sha256"
MAX_TEXT_INPUT_CHARS = 512


class PressKeyAction:
    name = "press_key"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        key = request.arguments.get("key")
        if is_destructive_window_key(key):
            return ActionRisk.DESTRUCTIVE
        return ActionRisk.CONFIRM

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        key = request.arguments.get("key")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not is_allowed_window_key(key)
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Entrada de tecla bloqueada antes da confirmação: argumentos inválidos.",
            )

        normalized_title = title.strip()
        key_effect = (
            "ATENÇÃO: BACKSPACE e DELETE podem remover texto, itens ou outros dados "
            "dependendo do controle que estiver em foco. O efeito interno do aplicativo "
            "não será inspecionado."
            if is_destructive_window_key(key)
            else (
                "A tecla pertence à allowlist de confirmação para navegação ou controle "
                "pontual da janela."
            )
        )
        return ConfirmationPreview(
            allowed=True,
            text=(
                "PRESSIONAR TECLA EM JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Tecla: {key}\n"
                f"{key_effect}\n"
                "ENTER pode confirmar/enviar, ESCAPE pode cancelar/fechar um estado "
                "transitório, TAB pode mover o foco entre controles, UP/DOWN/LEFT/RIGHT "
                "podem navegar direcionalmente, HOME/END/PAGE_UP/PAGE_DOWN podem navegar "
                "por limites ou páginas e BACKSPACE/DELETE são teclas de edição destrutiva. "
                "Após a confirmação, o THE OS reativará somente a janela exata aprovada e "
                "verificará que ela "
                "está em primeiro plano antes de enviar a tecla. O THE OS verifica o envio "
                "dos eventos e o foco, mas não lê o conteúdo ou o estado interno do "
                "aplicativo para afirmar qual efeito a tecla produziu."
            ),
            execution_guard={
                _EXPECTED_KEY_PID: pid,
                _EXPECTED_KEY_TITLE: normalized_title,
                _EXPECTED_KEY_TARGET_TOKEN: target_token,
                _EXPECTED_KEY_NAME: key,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        key = request.arguments.get("key")
        expected_pid = request.arguments.get(_EXPECTED_KEY_PID)
        expected_title = request.arguments.get(_EXPECTED_KEY_TITLE)
        expected_target_token = request.arguments.get(_EXPECTED_KEY_TARGET_TOKEN)
        expected_key = request.arguments.get(_EXPECTED_KEY_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not is_allowed_window_key(key)
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_key != key
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A entrada de tecla não possui uma prévia local aprovada.",
                error_code="KEY_INPUT_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.press_key(
                pid,
                title.strip(),
                target_token,
                key,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_KEY_INPUT_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou entrada de tecla na própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_KEY_INPUT_BLOCKED",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a entrada de tecla foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "KEY_INPUT_TARGET_ACTIVATION_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; a tecla não foi enviada."
                    ),
                    evidence={"reason": reason},
                    error_code="KEY_INPUT_TARGET_ACTIVATION_NOT_VERIFIED",
                )
            if reason == "KEY_INPUT_FOREGROUND_CHANGED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O foco mudou durante a entrada; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    evidence={"reason": reason},
                    error_code="KEY_INPUT_FOREGROUND_CHANGED",
                )
            if reason == "KEY_INPUT_NOT_ALLOWED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Essa tecla não está permitida nesta etapa.",
                    evidence={"reason": reason},
                    error_code="KEY_INPUT_NOT_ALLOWED",
                )
            if reason == "KEY_INPUT_NOT_ACCEPTED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou o envio completo da tecla.",
                    evidence={"reason": reason},
                    error_code="KEY_INPUT_NOT_ACCEPTED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar a tecla para essa janela.",
                evidence={"reason": reason},
                error_code="KEY_INPUT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar a tecla para essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="KEY_INPUT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Tecla {key} enviada ao alvo: {evidence['title']} "
                f"(PID {evidence['pid']}); eventos e foco verificados, "
                "efeito interno não inspecionado."
            ),
            evidence=evidence,
        )



class PressShortcutAction:
    name = "press_shortcut"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        shortcut = request.arguments.get("shortcut")
        if is_privileged_window_shortcut(shortcut):
            return ActionRisk.PRIVILEGED
        if is_destructive_window_shortcut(shortcut):
            return ActionRisk.DESTRUCTIVE
        return ActionRisk.CONFIRM

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        shortcut = request.arguments.get("shortcut")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not is_allowed_window_shortcut(shortcut)
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Atalho de teclado bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        shortcut_label = {
            "CTRL_A": "CTRL+A",
            "CTRL_C": "CTRL+C",
            "CTRL_X": "CTRL+X",
            "CTRL_V": "CTRL+V",
            "CTRL_Z": "CTRL+Z",
        }[shortcut]
        if shortcut == "CTRL_A":
            shortcut_effect = (
                "CTRL+A pode selecionar conteúdo dependendo do controle em foco. "
                "Nenhum conteúdo da área de transferência é lido ou escrito por esse atalho."
            )
        elif shortcut == "CTRL_C":
            shortcut_effect = (
                "ATENÇÃO: CTRL+C pode substituir o conteúdo atual da área de transferência "
                "pelo conteúdo selecionado no aplicativo. O THE OS não lê a área de "
                "transferência e não verifica semanticamente o que foi copiado."
            )
        elif shortcut == "CTRL_X":
            shortcut_effect = (
                "ATENÇÃO: CTRL+X pode remover o conteúdo selecionado do aplicativo e "
                "substituir o conteúdo atual da área de transferência. O THE OS não lê a "
                "área de transferência e não verifica semanticamente o que foi recortado."
            )
        elif shortcut == "CTRL_V":
            shortcut_effect = (
                "PRIVILEGIADO: CTRL+V pode inserir no aplicativo alvo o conteúdo atual da "
                "área de transferência, que pode conter dados sensíveis. O THE OS não lê, "
                "não mostra ao provedor e não pré-visualiza esse conteúdo; portanto não pode "
                "inspecionar o que será colado antes do envio."
            )
        else:
            shortcut_effect = (
                "ATENÇÃO: CTRL+Z pode desfazer a última operação no controle em foco e "
                "alterar, remover ou restaurar conteúdo. O THE OS não inspeciona o histórico "
                "de desfazer e não verifica semanticamente o resultado."
            )
        return ConfirmationPreview(
            allowed=True,
            text=(
                "PRESSIONAR ATALHO EM JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Atalho: {shortcut_label}\n"
                "Somente CTRL+A, CTRL+C, CTRL+X, CTRL+V e CTRL+Z estão permitidos nesta etapa. "
                f"{shortcut_effect} "
                "Após a confirmação, o THE OS reativará somente a janela exata aprovada, "
                "verificará o primeiro plano, enviará o atalho como uma sequência fixa "
                "de quatro eventos e verificará novamente o foco."
            ),
            execution_guard={
                _EXPECTED_SHORTCUT_PID: pid,
                _EXPECTED_SHORTCUT_TITLE: normalized_title,
                _EXPECTED_SHORTCUT_TARGET_TOKEN: target_token,
                _EXPECTED_SHORTCUT_NAME: shortcut,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        shortcut = request.arguments.get("shortcut")
        expected_pid = request.arguments.get(_EXPECTED_SHORTCUT_PID)
        expected_title = request.arguments.get(_EXPECTED_SHORTCUT_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_SHORTCUT_TARGET_TOKEN
        )
        expected_shortcut = request.arguments.get(_EXPECTED_SHORTCUT_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not is_allowed_window_shortcut(shortcut)
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_shortcut != shortcut
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O atalho não possui uma prévia local aprovada.",
                error_code="SHORTCUT_INPUT_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.press_shortcut(
                pid,
                title.strip(),
                target_token,
                shortcut,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_SHORTCUT_INPUT_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou atalho de teclado na própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_SHORTCUT_INPUT_BLOCKED",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o atalho foi bloqueado."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "SHORTCUT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; o atalho não foi enviado."
                    ),
                    evidence={"reason": reason},
                    error_code="SHORTCUT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED",
                )
            if reason == "SHORTCUT_INPUT_FOREGROUND_CHANGED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O foco mudou durante o atalho; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    evidence={"reason": reason},
                    error_code="SHORTCUT_INPUT_FOREGROUND_CHANGED",
                )
            if reason == "SHORTCUT_INPUT_NOT_ALLOWED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Esse atalho não está permitido nesta etapa.",
                    evidence={"reason": reason},
                    error_code="SHORTCUT_INPUT_NOT_ALLOWED",
                )
            if reason == "SHORTCUT_INPUT_NOT_ACCEPTED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou o envio completo do atalho.",
                    evidence={"reason": reason},
                    error_code="SHORTCUT_INPUT_NOT_ACCEPTED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o atalho para essa janela.",
                evidence={"reason": reason},
                error_code="SHORTCUT_INPUT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o atalho para essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="SHORTCUT_INPUT_FAILED",
            )

        shortcut_label = {
            "CTRL_A": "CTRL+A",
            "CTRL_C": "CTRL+C",
            "CTRL_X": "CTRL+X",
            "CTRL_V": "CTRL+V",
            "CTRL_Z": "CTRL+Z",
        }[shortcut]
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Atalho {shortcut_label} enviado ao alvo: {evidence['title']} "
                f"(PID {evidence['pid']}); eventos e foco verificados, "
                "efeito interno não inspecionado."
            ),
            evidence=evidence,
        )


class TypeTextAction:
    name = "type_text"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        text = request.arguments.get("text")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not isinstance(text, str)
            or not text
            or len(text) > MAX_TEXT_INPUT_CHARS
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in text)
            or any(0xD800 <= ord(character) <= 0xDFFF for character in text)
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Entrada de texto bloqueada antes da confirmação: argumentos inválidos.",
            )

        normalized_title = title.strip()
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "DIGITAR TEXTO EM JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Caracteres: {len(text)}\n"
                f"Texto exato:\n{text}\n"
                "A LYRA enviará somente caracteres Unicode comuns para a janela alvo. "
                "Enter, Tab, atalhos, teclas especiais e caracteres de controle não são "
                "permitidos. Após a confirmação, o THE OS reativará somente a janela "
                "exata aprovada pelo token opaco e verificará que ela está em primeiro "
                "plano antes de enviar o texto. O THE OS verifica o envio dos eventos "
                "e o foco, mas não lê o conteúdo da janela para afirmar onde o texto apareceu."
            ),
            execution_guard={
                _EXPECTED_TEXT_PID: pid,
                _EXPECTED_TEXT_TITLE: normalized_title,
                _EXPECTED_TEXT_TARGET_TOKEN: target_token,
                _EXPECTED_TEXT_SHA256: text_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        text = request.arguments.get("text")
        expected_pid = request.arguments.get(_EXPECTED_TEXT_PID)
        expected_title = request.arguments.get(_EXPECTED_TEXT_TITLE)
        expected_target_token = request.arguments.get(_EXPECTED_TEXT_TARGET_TOKEN)
        expected_sha256 = request.arguments.get(_EXPECTED_TEXT_SHA256)

        valid_text = (
            isinstance(text, str)
            and bool(text)
            and len(text) <= MAX_TEXT_INPUT_CHARS
            and not any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in text
            )
            and not any(0xD800 <= ord(character) <= 0xDFFF for character in text)
        )
        current_sha256 = (
            hashlib.sha256(text.encode("utf-8")).hexdigest()
            if valid_text
            else None
        )

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or not valid_text
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_sha256 != current_sha256
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A entrada de texto não possui uma prévia local aprovada.",
                error_code="TEXT_INPUT_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.type_text(
                pid,
                title.strip(),
                target_token,
                text,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_TEXT_INPUT_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou entrada de texto na própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_TEXT_INPUT_BLOCKED",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a entrada de texto foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "TEXT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; a entrada de texto foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="TEXT_INPUT_TARGET_ACTIVATION_NOT_VERIFIED",
                )
            if reason == "TEXT_INPUT_FOREGROUND_CHANGED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O foco mudou durante a entrada; não posso confirmar "
                        "que todos os eventos permaneceram no alvo."
                    ),
                    evidence={"reason": reason},
                    error_code="TEXT_INPUT_FOREGROUND_CHANGED",
                )
            if reason in {
                "TEXT_INPUT_INVALID",
                "TEXT_INPUT_CONTROL_CHAR_BLOCKED",
                "TEXT_INPUT_INVALID_UNICODE",
            }:
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O texto solicitado não é permitido para esta ação.",
                    evidence={"reason": reason},
                    error_code="TEXT_INPUT_INVALID",
                )
            if reason == "TEXT_INPUT_NOT_ACCEPTED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou o envio de todos os eventos de texto.",
                    evidence={"reason": reason},
                    error_code="TEXT_INPUT_NOT_ACCEPTED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o texto para essa janela.",
                evidence={"reason": reason},
                error_code="TEXT_INPUT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o texto para essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="TEXT_INPUT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Entrada de texto enviada ao alvo: {evidence['title']} "
                f"(PID {evidence['pid']}); eventos e foco verificados, "
                "conteúdo interno não inspecionado."
            ),
            evidence=evidence,
        )


class RestoreWindowAction:
    name = "restore_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="PID, título e alvo opaco exatos da janela são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.restore_window(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_RESTORE_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou a restauração da própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_RESTORE_BLOCKED",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a restauração foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_RESTORE_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou a janela exata em tamanho normal.",
                    evidence={"reason": reason},
                    error_code="WINDOW_RESTORE_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui restaurar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_RESTORE_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui restaurar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_RESTORE_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata restaurada e verificada em tamanho normal: "
                f"{evidence['title']} (PID {evidence['pid']})."
            ),
            evidence=evidence,
        )


class MaximizeWindowAction:
    name = "maximize_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="PID, título e alvo opaco exatos da janela são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.maximize_window(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_MAXIMIZE_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou a maximização da própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_MAXIMIZE_BLOCKED",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a maximização foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_MAXIMIZE_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou a janela exata como maximizada.",
                    evidence={"reason": reason},
                    error_code="WINDOW_MAXIMIZE_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui maximizar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_MAXIMIZE_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui maximizar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_MAXIMIZE_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata maximizada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']})."
            ),
            evidence=evidence,
        )


class MinimizeWindowAction:
    name = "minimize_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="PID, título e alvo opaco exatos da janela são obrigatórios.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.minimize_window(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_MINIMIZE_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou a minimização da própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_MINIMIZE_BLOCKED",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei essa janela visível exata.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a minimização foi bloqueada."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_MINIMIZE_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O Windows não confirmou a janela exata como minimizada.",
                    evidence={"reason": reason},
                    error_code="WINDOW_MINIMIZE_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui minimizar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_MINIMIZE_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui minimizar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_MINIMIZE_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata minimizada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']})."
            ),
            evidence=evidence,
        )


_EXPECTED_CLOSE_PID = "_theos_expected_close_pid"
_EXPECTED_CLOSE_TITLE = "_theos_expected_close_title"
_EXPECTED_CLOSE_TARGET_TOKEN = "_theos_expected_close_target_token"


class CloseWindowAction:
    name = "close_window"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Fechamento bloqueado antes da confirmação: alvo inválido.",
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "FECHAR JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                "Atenção: fechar a janela pode descartar trabalho não salvo ou fazer "
                "o aplicativo exibir uma confirmação própria.\n"
                "A LYRA enviará somente o comando normal de fechar a janela "
                "(WM_SYSCOMMAND/SC_CLOSE) para o alvo exato aprovado; não haverá "
                "encerramento forçado do processo."
            ),
            execution_guard={
                _EXPECTED_CLOSE_PID: pid,
                _EXPECTED_CLOSE_TITLE: normalized_title,
                _EXPECTED_CLOSE_TARGET_TOKEN: target_token,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        expected_pid = request.arguments.get(_EXPECTED_CLOSE_PID)
        expected_title = request.arguments.get(_EXPECTED_CLOSE_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_CLOSE_TARGET_TOKEN
        )

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O fechamento não possui uma prévia local aprovada.",
                error_code="WINDOW_CLOSE_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.close_window(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "SELF_WINDOW_CLOSE_BLOCKED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="A LYRA bloqueou o fechamento da própria janela.",
                    evidence={"reason": reason},
                    error_code="SELF_WINDOW_CLOSE_BLOCKED",
                )
            if reason == "WINDOW_TARGET_TOKEN_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="O identificador opaco da janela é inválido.",
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_TOKEN_INVALID",
                )
            if reason == "WINDOW_TARGET_TOKEN_STALE":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "A janela ainda existe com o mesmo PID e título, mas o token "
                        "opaco mudou antes do fechamento; a ação foi bloqueada."
                    ),
                    evidence={
                        "reason": reason,
                        "diagnosis": "same_pid_title_but_target_token_changed",
                    },
                    error_code="WINDOW_TARGET_TOKEN_STALE",
                )
            if reason == "WINDOW_TARGET_TITLE_CHANGED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O processo alvo ainda possui janela visível, mas o título "
                        "mudou antes do fechamento; a ação foi bloqueada."
                    ),
                    evidence={
                        "reason": reason,
                        "diagnosis": "same_pid_but_bounded_title_changed",
                    },
                    error_code="WINDOW_TARGET_TITLE_CHANGED",
                )
            if reason == "WINDOW_TARGET_NOT_FOUND":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Não encontrei mais uma janela visível para esse PID.",
                    evidence={
                        "reason": reason,
                        "diagnosis": "no_visible_window_for_pid",
                    },
                    error_code="WINDOW_TARGET_NOT_FOUND",
                )
            if reason == "WINDOW_TARGET_AMBIGUOUS":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o fechamento foi bloqueado."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_TARGET_AMBIGUOUS",
                )
            if reason == "WINDOW_CLOSE_NOT_VERIFIED":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=(
                        "O Windows recebeu a solicitação, mas a janela exata continuou "
                        "aberta; pode haver uma confirmação do próprio aplicativo."
                    ),
                    evidence={"reason": reason},
                    error_code="WINDOW_CLOSE_NOT_VERIFIED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui fechar essa janela.",
                evidence={"reason": reason},
                error_code="WINDOW_CLOSE_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui solicitar o fechamento dessa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_CLOSE_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata fechada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']})."
            ),
            evidence=evidence,
        )
