from __future__ import annotations

import hashlib

from theos.core.actions.contracts import (
    ActionRequest,
    ActionResult,
    ActionRisk,
    ConfirmationPreview,
)
from theos.core.keyboard_keys import (
    format_window_key_allowlist_pt,
    get_window_key_spec,
)
from theos.core.keyboard_shortcuts import (
    format_window_shortcut_allowlist_pt,
    get_window_shortcut_spec,
)
from theos.core.mouse_anchors import (
    format_mouse_anchor_allowlist_pt,
    get_mouse_anchor_spec,
)
from theos.core.mouse_clicks import (
    format_mouse_button_allowlist_pt,
    get_mouse_button_spec,
)
from theos.core.mouse_drags import get_mouse_drag_spec
from theos.core.mouse_gestures import get_mouse_gesture_spec
from theos.core.mouse_scroll import (
    format_mouse_scroll_allowlist_pt,
    get_mouse_scroll_spec,
)
from theos.core.window_layout_pairs import get_window_pair_layout_spec
from theos.core.window_layout_sets import get_window_set_layout_spec
from theos.core.window_observations import (
    WindowObservationHandleError,
    validate_window_observation_handle,
)
from theos.core.window_placements import get_window_placement_spec
from theos.core.window_semantics import (
    MAX_SEMANTIC_NAME_CHARS,
    is_semantic_control_token,
)
from theos.core.window_targets import (
    is_window_target_token,
    normalize_window_queries,
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
                "PID, um token opaco de alvo e uma referência de observação "
                "temporária assinada gerados localmente.\n"
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




class WindowSnapshotManyAction:
    name = "window_snapshot_many"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        normalized_queries = normalize_window_queries(
            request.arguments.get("queries")
        )
        if normalized_queries is None:
            return ConfirmationPreview(
                allowed=False,
                text="Inspeção multi-alvo de janelas bloqueada: filtros locais inválidos.",
            )

        filters = "; ".join(normalized_queries)
        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR MÚLTIPLAS JANELAS VISÍVEIS\n"
                "A LYRA enumerará localmente as janelas de nível superior que estão "
                "visíveis uma única vez e enviará ao provedor de IA somente as janelas "
                "que corresponderem a pelo menos um dos filtros literais aprovados, "
                "incluindo uma referência de observação temporária assinada por alvo.\n"
                f"Filtros locais solicitados ({len(normalized_queries)}): {filters}\n"
                "Correspondência: substring determinística sem regex ou fuzzy match, "
                "aplicada somente ao título limitado ou nome do processo.\n"
                "Limite global de saída: 12 janelas; títulos são limitados a "
                "160 caracteres.\n"
                "Não serão coletados conteúdo interno das janelas, teclas digitadas, "
                "capturas de tela, caminhos de executáveis, handles brutos ou títulos "
                "de janelas ocultas."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        normalized_queries = normalize_window_queries(
            request.arguments.get("queries")
        )
        if normalized_queries is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Os filtros locais da inspeção multi-alvo são inválidos.",
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.snapshot_many(normalized_queries)
        except RuntimeError as exc:
            reason = str(exc)
            if reason == "WINDOW_QUERIES_INVALID":
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message="Os filtros locais da inspeção multi-alvo são inválidos.",
                    evidence={"reason": reason},
                    error_code="ACTION_VALIDATION_FAILED",
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar as janelas visíveis solicitadas.",
                evidence={"reason": reason},
                error_code="WINDOW_SNAPSHOT_MANY_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar as janelas visíveis solicitadas.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_SNAPSHOT_MANY_FAILED",
            )

        observed = int(evidence["observed_windows"])
        matched = int(evidence["matched_windows"])
        returned = int(evidence["returned_windows"])
        filter_count = int(evidence["filter_count"])
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janelas inspecionadas: {observed} visíveis com título; "
                f"{matched} corresponderam a pelo menos um dos {filter_count} filtros "
                f"locais; {returned} retornadas."
            ),
            evidence=evidence,
        )
class SemanticWindowSnapshotAction:
    name = "semantic_window_snapshot"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def _validated_arguments(
        request: ActionRequest,
    ) -> tuple[int, str, str, dict[str, object]] | None:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        observation_handle = request.arguments.get("observation_handle")

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or observation_handle is None
        ):
            return None

        try:
            validated_handle = validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError:
            return None

        return pid, title.strip(), target_token, validated_handle

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        validated = SemanticWindowSnapshotAction._validated_arguments(request)
        if validated is None:
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Inspeção semântica bloqueada: alvo ou referência de observação "
                    "inválidos, incompatíveis ou expirados."
                ),
            )

        pid, title, target_token, _handle = validated
        return ConfirmationPreview(
            allowed=True,
            text=(
                "INSPECIONAR CONTROLES SEMÂNTICOS NATIVOS\n"
                f"Janela exata: {title} (PID {pid}).\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                "A referência de observação recente será revalidada localmente antes "
                "da inspeção.\n"
                "O THE HANDS enumerará somente controles filhos Win32 visíveis da "
                "janela exata e retornará no máximo 32 controles com papel derivado "
                "da classe, classe nativa, ID de controle quando disponível, estado "
                "habilitado e token opaco do controle.\n"
                "Nomes limitados poderão ser coletados apenas de controles Button e "
                "Static. Valores de campos de texto/Edit/RichEdit não serão coletados.\n"
                "Não serão coletados capturas de tela, valores digitados, caminhos de "
                "executáveis ou handles HWND brutos. Nenhuma ação por coordenadas será "
                "executada nesta inspeção."
            ),
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        observation_handle = request.arguments.get("observation_handle")

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or observation_handle is None
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "PID, título, token opaco e referência de observação recente "
                    "são obrigatórios para a inspeção semântica."
                ),
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError as exc:
            messages = {
                "WINDOW_OBSERVATION_EXPIRED": (
                    "A observação da janela expirou; inspecione a janela novamente."
                ),
                "WINDOW_OBSERVATION_TARGET_MISMATCH": (
                    "A referência de observação não pertence a essa janela."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=messages.get(
                    exc.code,
                    "A referência de observação da janela é inválida.",
                ),
                evidence={"reason": exc.code},
                error_code=exc.code,
            )

        try:
            evidence = self._windows.semantic_window_snapshot(
                pid,
                title.strip(),
                target_token,
            )
        except RuntimeError as exc:
            reason = str(exc)
            known = {
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido."
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata."
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    "Mais de uma janela correspondeu ao alvo opaco."
                ),
                "WINDOW_VISUAL_FRAME_NOT_FOUND": (
                    "Não encontrei a moldura visual da janela exata."
                ),
                "WINDOW_VISUAL_FRAME_AMBIGUOUS": (
                    "A moldura visual da janela ficou ambígua."
                ),
            }
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=known.get(
                    reason,
                    "Não consegui inspecionar os controles semânticos nativos.",
                ),
                evidence={"reason": reason},
                error_code=(
                    reason
                    if reason in known
                    else "SEMANTIC_WINDOW_SNAPSHOT_FAILED"
                ),
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui inspecionar os controles semânticos nativos.",
                evidence={"exception": type(exc).__name__},
                error_code="SEMANTIC_WINDOW_SNAPSHOT_FAILED",
            )

        visible = int(evidence["visible_native_controls"])
        returned = int(evidence["returned_controls"])
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                "Controles semânticos nativos inspecionados: "
                f"{visible} visíveis; {returned} retornados. "
                "Valores de campos de texto não foram coletados."
            ),
            evidence=evidence,
        )


_EXPECTED_SEMANTIC_BUTTON_PID = "_theos_expected_semantic_button_pid"
_EXPECTED_SEMANTIC_BUTTON_TITLE = "_theos_expected_semantic_button_title"
_EXPECTED_SEMANTIC_BUTTON_TARGET_TOKEN = (
    "_theos_expected_semantic_button_target_token"
)
_EXPECTED_SEMANTIC_BUTTON_OBSERVATION_HANDLE = (
    "_theos_expected_semantic_button_observation_handle"
)
_EXPECTED_SEMANTIC_BUTTON_CONTROL_TOKEN = (
    "_theos_expected_semantic_button_control_token"
)
_EXPECTED_SEMANTIC_BUTTON_NAME = "_theos_expected_semantic_button_name"
_EXPECTED_SEMANTIC_BUTTON_CONTROL_ID = (
    "_theos_expected_semantic_button_control_id"
)


class InvokeSemanticButtonAction:
    name = "invoke_semantic_button"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def _validated_arguments(
        request: ActionRequest,
    ) -> tuple[
        int,
        str,
        str,
        dict[str, object],
        str,
        str,
        int | None,
    ] | None:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        observation_handle = request.arguments.get("observation_handle")
        control_token = request.arguments.get("control_token")
        role = request.arguments.get("role")
        name = request.arguments.get("name")
        class_name = request.arguments.get("class_name")
        control_id = request.arguments.get("control_id")
        enabled = request.arguments.get("enabled")

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or observation_handle is None
            or not is_semantic_control_token(control_token)
            or role != "button"
            or not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > MAX_SEMANTIC_NAME_CHARS
            or class_name != "Button"
            or (
                control_id is not None
                and (
                    not isinstance(control_id, int)
                    or isinstance(control_id, bool)
                    or control_id < 0
                )
            )
            or enabled is not True
        ):
            return None

        try:
            validated_handle = validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError:
            return None

        return (
            pid,
            title.strip(),
            target_token,
            validated_handle,
            control_token,
            name.strip(),
            control_id,
        )

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        validated = InvokeSemanticButtonAction._validated_arguments(request)
        if validated is None:
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Invocação semântica bloqueada antes da confirmação: "
                    "alvo, observação ou botão inválidos."
                ),
            )

        (
            pid,
            title,
            target_token,
            observation_handle,
            control_token,
            name,
            control_id,
        ) = validated
        control_id_text = (
            "indisponível"
            if control_id is None
            else str(control_id)
        )
        return ConfirmationPreview(
            allowed=True,
            text=(
                "ACIONAR BOTÃO SEMÂNTICO NATIVO\n"
                f"Janela exata: {title} (PID {pid}).\n"
                f"Botão: {name}\n"
                f"ID de controle: {control_id_text}\n"
                f"Alvo da janela: {target_token[:12]}...\n"
                f"Token do controle: {control_token[:12]}...\n"
                "Após a confirmação, o THE HANDS revalidará a observação da janela "
                "e enumerará novamente seus controles Win32. Somente o Button visível "
                "e habilitado que ainda corresponda ao token e metadados aprovados "
                "poderá ser acionado.\n"
                "A invocação usa BM_CLICK nativo com timeout limitado e não usa "
                "coordenadas, movimento do cursor ou texto digitado. O despacho do "
                "evento pode ser confirmado; o efeito interno do aplicativo não será "
                "tratado como objetivo verificado."
            ),
            execution_guard={
                _EXPECTED_SEMANTIC_BUTTON_PID: pid,
                _EXPECTED_SEMANTIC_BUTTON_TITLE: title,
                _EXPECTED_SEMANTIC_BUTTON_TARGET_TOKEN: target_token,
                _EXPECTED_SEMANTIC_BUTTON_OBSERVATION_HANDLE: observation_handle,
                _EXPECTED_SEMANTIC_BUTTON_CONTROL_TOKEN: control_token,
                _EXPECTED_SEMANTIC_BUTTON_NAME: name,
                _EXPECTED_SEMANTIC_BUTTON_CONTROL_ID: control_id,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        validated = self._validated_arguments(request)
        if validated is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A invocação do botão semântico não possui argumentos "
                    "válidos e recentemente observados."
                ),
                error_code="SEMANTIC_BUTTON_ARGUMENTS_INVALID",
            )

        (
            pid,
            title,
            target_token,
            observation_handle,
            control_token,
            name,
            control_id,
        ) = validated

        if (
            request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_PID) != pid
            or request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_TITLE) != title
            or request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_TARGET_TOKEN)
            != target_token
            or request.arguments.get(
                _EXPECTED_SEMANTIC_BUTTON_OBSERVATION_HANDLE
            )
            != observation_handle
            or request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_CONTROL_TOKEN)
            != control_token
            or request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_NAME) != name
            or request.arguments.get(_EXPECTED_SEMANTIC_BUTTON_CONTROL_ID)
            != control_id
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "O botão semântico não possui uma prévia local aprovada "
                    "para estes metadados exatos."
                ),
                error_code="SEMANTIC_BUTTON_PREVIEW_REQUIRED",
            )

        try:
            validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A observação da janela não é mais válida; "
                    "inspecione a janela novamente."
                ),
                evidence={"reason": exc.code},
                error_code=exc.code,
            )

        try:
            evidence = self._windows.invoke_semantic_button(
                pid,
                title,
                target_token,
                control_token,
                name,
                control_id,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_SEMANTIC_BUTTON_INVOKE_BLOCKED": (
                    "A LYRA bloqueou a invocação semântica na própria janela.",
                    "SELF_WINDOW_SEMANTIC_BUTTON_INVOKE_BLOCKED",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    "Mais de uma janela correspondeu ao alvo opaco.",
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_VISUAL_FRAME_NOT_FOUND": (
                    "Não encontrei a moldura visual da janela exata.",
                    "WINDOW_VISUAL_FRAME_NOT_FOUND",
                ),
                "WINDOW_VISUAL_FRAME_AMBIGUOUS": (
                    "A moldura visual da janela ficou ambígua.",
                    "WINDOW_VISUAL_FRAME_AMBIGUOUS",
                ),
                "SEMANTIC_CONTROL_TOKEN_INVALID": (
                    "O token opaco do controle é inválido.",
                    "SEMANTIC_CONTROL_TOKEN_INVALID",
                ),
                "SEMANTIC_CONTROL_NOT_FOUND_OR_STALE": (
                    "O botão semântico não existe mais; inspecione a janela novamente.",
                    "SEMANTIC_CONTROL_NOT_FOUND_OR_STALE",
                ),
                "SEMANTIC_CONTROL_AMBIGUOUS": (
                    "O controle semântico ficou ambíguo e não foi acionado.",
                    "SEMANTIC_CONTROL_AMBIGUOUS",
                ),
                "SEMANTIC_CONTROL_NOT_BUTTON": (
                    "O controle observado não é mais um botão nativo.",
                    "SEMANTIC_CONTROL_NOT_BUTTON",
                ),
                "SEMANTIC_CONTROL_METADATA_CHANGED": (
                    "Os metadados do botão mudaram; inspecione a janela novamente.",
                    "SEMANTIC_CONTROL_METADATA_CHANGED",
                ),
                "SEMANTIC_CONTROL_NOT_VISIBLE": (
                    "O botão semântico não está mais visível.",
                    "SEMANTIC_CONTROL_NOT_VISIBLE",
                ),
                "SEMANTIC_CONTROL_DISABLED": (
                    "O botão semântico está desabilitado e não foi acionado.",
                    "SEMANTIC_CONTROL_DISABLED",
                ),
                "SEMANTIC_BUTTON_INVOKE_NOT_ACCEPTED": (
                    "O Windows não confirmou o despacho da invocação do botão.",
                    "SEMANTIC_BUTTON_INVOKE_NOT_ACCEPTED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui acionar esse botão semântico nativo.",
                evidence={"reason": reason},
                error_code="SEMANTIC_BUTTON_INVOKE_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui acionar esse botão semântico nativo.",
                evidence={"exception": type(exc).__name__},
                error_code="SEMANTIC_BUTTON_INVOKE_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Botão semântico acionado: {evidence['name']} em "
                f"{evidence['title']} (PID {evidence['pid']}); "
                "despacho nativo verificado, efeito interno não inspecionado."
            ),
            evidence=evidence,
            effect_dispatched=True,
            postcondition_verified=None,
        )


_EXPECTED_SEMANTIC_TEXT_PID = "_theos_expected_semantic_text_pid"
_EXPECTED_SEMANTIC_TEXT_TITLE = "_theos_expected_semantic_text_title"
_EXPECTED_SEMANTIC_TEXT_TARGET_TOKEN = "_theos_expected_semantic_text_target_token"
_EXPECTED_SEMANTIC_TEXT_OBSERVATION_HANDLE = (
    "_theos_expected_semantic_text_observation_handle"
)
_EXPECTED_SEMANTIC_TEXT_CONTROL_TOKEN = "_theos_expected_semantic_text_control_token"
_EXPECTED_SEMANTIC_TEXT_CONTROL_ID = "_theos_expected_semantic_text_control_id"
_EXPECTED_SEMANTIC_TEXT_SHA256 = "_theos_expected_semantic_text_sha256"


class SetSemanticTextAction:
    name = "set_semantic_text"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def _validated_arguments(
        request: ActionRequest,
    ) -> tuple[int, str, str, dict[str, object], str, int | None, str] | None:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        observation_handle = request.arguments.get("observation_handle")
        control_token = request.arguments.get("control_token")
        role = request.arguments.get("role")
        class_name = request.arguments.get("class_name")
        control_id = request.arguments.get("control_id")
        enabled = request.arguments.get("enabled")
        text = request.arguments.get("text")

        valid_text = (
            isinstance(text, str)
            and bool(text)
            and len(text) <= MAX_TEXT_INPUT_CHARS
            and not any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in text
            )
            and not any(
                0xD800 <= ord(character) <= 0xDFFF
                for character in text
            )
        )
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or observation_handle is None
            or not is_semantic_control_token(control_token)
            or role != "text_editor"
            or class_name != "Edit"
            or (
                control_id is not None
                and (
                    not isinstance(control_id, int)
                    or isinstance(control_id, bool)
                    or control_id < 0
                )
            )
            or enabled is not True
            or not valid_text
        ):
            return None

        try:
            validated_handle = validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError:
            return None

        assert isinstance(text, str)
        return (
            pid,
            title.strip(),
            target_token,
            validated_handle,
            control_token,
            control_id,
            text,
        )

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        validated = SetSemanticTextAction._validated_arguments(request)
        if validated is None:
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Substituição semântica de texto bloqueada antes da confirmação: "
                    "alvo, observação, Edit ou texto inválidos."
                ),
            )

        (
            pid,
            title,
            target_token,
            observation_handle,
            control_token,
            control_id,
            text,
        ) = validated
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        control_id_text = "indisponível" if control_id is None else str(control_id)
        return ConfirmationPreview(
            allowed=True,
            text=(
                "SUBSTITUIR TEXTO DE EDIT SEMÂNTICO NATIVO\n"
                f"Janela exata: {title} (PID {pid}).\n"
                f"ID de controle: {control_id_text}\n"
                f"Alvo da janela: {target_token[:12]}...\n"
                f"Token do controle: {control_token[:12]}...\n"
                f"Caracteres: {len(text)}\n"
                f"Texto exato que substituirá todo o valor atual:\n{text}\n"
                "Após a confirmação, o THE HANDS revalidará a observação da janela "
                "e enumerará novamente seus controles Win32. Somente o Edit visível "
                "e habilitado que ainda corresponda ao token e ID aprovados poderá "
                "receber o texto. Campos password e read-only são bloqueados. "
                "A operação usa WM_SETTEXT nativo com timeout, sem mover o cursor, "
                "sem teclado e sem clipboard. O conteúdo resultante é comparado "
                "localmente ao texto aprovado; o valor lido de volta não é enviado "
                "como evidência."
            ),
            execution_guard={
                _EXPECTED_SEMANTIC_TEXT_PID: pid,
                _EXPECTED_SEMANTIC_TEXT_TITLE: title,
                _EXPECTED_SEMANTIC_TEXT_TARGET_TOKEN: target_token,
                _EXPECTED_SEMANTIC_TEXT_OBSERVATION_HANDLE: observation_handle,
                _EXPECTED_SEMANTIC_TEXT_CONTROL_TOKEN: control_token,
                _EXPECTED_SEMANTIC_TEXT_CONTROL_ID: control_id,
                _EXPECTED_SEMANTIC_TEXT_SHA256: text_sha256,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        validated = self._validated_arguments(request)
        if validated is None:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A substituição semântica de texto não possui argumentos "
                    "válidos e recentemente observados."
                ),
                error_code="SEMANTIC_TEXT_ARGUMENTS_INVALID",
            )

        (
            pid,
            title,
            target_token,
            observation_handle,
            control_token,
            control_id,
            text,
        ) = validated
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if (
            request.arguments.get(_EXPECTED_SEMANTIC_TEXT_PID) != pid
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_TITLE) != title
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_TARGET_TOKEN)
            != target_token
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_OBSERVATION_HANDLE)
            != observation_handle
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_CONTROL_TOKEN)
            != control_token
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_CONTROL_ID) != control_id
            or request.arguments.get(_EXPECTED_SEMANTIC_TEXT_SHA256) != text_sha256
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A substituição semântica de texto não possui uma prévia local "
                    "aprovada para este controle e texto exatos."
                ),
                error_code="SEMANTIC_TEXT_PREVIEW_REQUIRED",
            )

        try:
            validate_window_observation_handle(
                observation_handle,
                expected_target_token=target_token,
            )
        except WindowObservationHandleError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "A observação da janela não é mais válida; "
                    "inspecione a janela novamente."
                ),
                evidence={"reason": exc.code},
                error_code=exc.code,
            )

        try:
            evidence = self._windows.set_semantic_text(
                pid,
                title,
                target_token,
                control_token,
                control_id,
                text,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_SEMANTIC_TEXT_BLOCKED": (
                    "A LYRA bloqueou texto semântico na própria janela.",
                    "SELF_WINDOW_SEMANTIC_TEXT_BLOCKED",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    "Mais de uma janela correspondeu ao alvo opaco.",
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_VISUAL_FRAME_NOT_FOUND": (
                    "Não encontrei a moldura visual da janela exata.",
                    "WINDOW_VISUAL_FRAME_NOT_FOUND",
                ),
                "WINDOW_VISUAL_FRAME_AMBIGUOUS": (
                    "A moldura visual da janela ficou ambígua.",
                    "WINDOW_VISUAL_FRAME_AMBIGUOUS",
                ),
                "SEMANTIC_CONTROL_TOKEN_INVALID": (
                    "O token opaco do controle é inválido.",
                    "SEMANTIC_CONTROL_TOKEN_INVALID",
                ),
                "SEMANTIC_CONTROL_NOT_FOUND_OR_STALE": (
                    "O Edit semântico não existe mais; inspecione novamente.",
                    "SEMANTIC_CONTROL_NOT_FOUND_OR_STALE",
                ),
                "SEMANTIC_CONTROL_AMBIGUOUS": (
                    "O controle semântico ficou ambíguo e não foi alterado.",
                    "SEMANTIC_CONTROL_AMBIGUOUS",
                ),
                "SEMANTIC_CONTROL_NOT_TEXT_EDITOR": (
                    "O controle observado não é mais um Edit nativo suportado.",
                    "SEMANTIC_CONTROL_NOT_TEXT_EDITOR",
                ),
                "SEMANTIC_CONTROL_METADATA_CHANGED": (
                    "Os metadados do Edit mudaram; inspecione novamente.",
                    "SEMANTIC_CONTROL_METADATA_CHANGED",
                ),
                "SEMANTIC_CONTROL_NOT_VISIBLE": (
                    "O Edit semântico não está mais visível.",
                    "SEMANTIC_CONTROL_NOT_VISIBLE",
                ),
                "SEMANTIC_CONTROL_DISABLED": (
                    "O Edit semântico está desabilitado.",
                    "SEMANTIC_CONTROL_DISABLED",
                ),
                "SEMANTIC_TEXT_PASSWORD_BLOCKED": (
                    "Campos Edit com estilo password não aceitam esta operação.",
                    "SEMANTIC_TEXT_PASSWORD_BLOCKED",
                ),
                "SEMANTIC_TEXT_READ_ONLY_BLOCKED": (
                    "Campos Edit read-only não aceitam esta operação.",
                    "SEMANTIC_TEXT_READ_ONLY_BLOCKED",
                ),
                "SEMANTIC_TEXT_SET_NOT_ACCEPTED": (
                    "O Windows não confirmou o despacho do WM_SETTEXT.",
                    "SEMANTIC_TEXT_SET_NOT_ACCEPTED",
                ),
                "SEMANTIC_TEXT_POSTCONDITION_NOT_VERIFIED": (
                    (
                        "O texto foi despachado, mas a leitura local não confirmou "
                        "o valor exato; a operação não será tratada como verificada."
                    ),
                    "SEMANTIC_TEXT_POSTCONDITION_NOT_VERIFIED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                postcondition_failure = (
                    reason == "SEMANTIC_TEXT_POSTCONDITION_NOT_VERIFIED"
                )
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                    effect_dispatched=True if postcondition_failure else None,
                    postcondition_verified=False if postcondition_failure else None,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui substituir o texto do Edit semântico.",
                evidence={"reason": reason},
                error_code="SEMANTIC_TEXT_SET_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui substituir o texto do Edit semântico.",
                evidence={"exception": type(exc).__name__},
                error_code="SEMANTIC_TEXT_SET_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Texto semântico substituído e verificado em "
                f"{evidence['title']} (PID {evidence['pid']}), "
                f"Edit ID {evidence['control_id']}."
            ),
            evidence=evidence,
            effect_dispatched=True,
            postcondition_verified=True,
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


_EXPECTED_MOUSE_PID = "_theos_expected_mouse_pid"
_EXPECTED_MOUSE_TITLE = "_theos_expected_mouse_title"
_EXPECTED_MOUSE_TARGET_TOKEN = "_theos_expected_mouse_target_token"
_EXPECTED_MOUSE_BUTTON = "_theos_expected_mouse_button"


class ClickWindowAction:
    name = "click_window"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        button_spec = get_mouse_button_spec(request.arguments.get("button"))
        if button_spec is None:
            return ActionRisk.CONFIRM
        return button_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        button = request.arguments.get("button")
        button_spec = get_mouse_button_spec(button)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or button_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Clique de mouse bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "CLICAR CENTRO DA JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Botão: {button}\n"
                f"Somente {format_mouse_button_allowlist_pt()} estão permitidos "
                "nesta etapa.\n"
                "Posição: centro geométrico da janela exata no momento da execução.\n"
                f"{button_spec.preview_effect}\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, calculará localmente o centro "
                "da janela, posicionará o cursor nesse ponto, enviará exatamente dois "
                "eventos de mouse e verificará novamente o foco. Coordenadas "
                "arbitrárias não são aceitas e o efeito interno não é inspecionado."
            ),
            execution_guard={
                _EXPECTED_MOUSE_PID: pid,
                _EXPECTED_MOUSE_TITLE: normalized_title,
                _EXPECTED_MOUSE_TARGET_TOKEN: target_token,
                _EXPECTED_MOUSE_BUTTON: button,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        button = request.arguments.get("button")
        button_spec = get_mouse_button_spec(button)
        expected_pid = request.arguments.get(_EXPECTED_MOUSE_PID)
        expected_title = request.arguments.get(_EXPECTED_MOUSE_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_MOUSE_TARGET_TOKEN
        )
        expected_button = request.arguments.get(_EXPECTED_MOUSE_BUTTON)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or button_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_button != button
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O clique de mouse não possui uma prévia local aprovada.",
                error_code="MOUSE_CLICK_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.click_window_center(
                pid,
                title.strip(),
                target_token,
                button,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_INPUT_BLOCKED": (
                    "A LYRA bloqueou clique de mouse na própria janela.",
                    "SELF_WINDOW_MOUSE_INPUT_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o clique foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_INPUT_TARGET_ACTIVATION_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; o clique não foi enviado."
                    ),
                    "MOUSE_INPUT_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_INPUT_WINDOW_RECT_INVALID": (
                    "A geometria da janela alvo não pôde ser validada.",
                    "MOUSE_INPUT_WINDOW_RECT_INVALID",
                ),
                "MOUSE_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor no centro da janela.",
                    "MOUSE_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_INPUT_NOT_ALLOWED": (
                    "Esse botão do mouse não está permitido nesta etapa.",
                    "MOUSE_INPUT_NOT_ALLOWED",
                ),
                "MOUSE_INPUT_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio completo do clique.",
                    "MOUSE_INPUT_NOT_ACCEPTED",
                ),
                "MOUSE_INPUT_FOREGROUND_CHANGED": (
                    (
                        "O foco mudou durante o clique; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    "MOUSE_INPUT_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui clicar nessa janela.",
                evidence={"reason": reason},
                error_code="MOUSE_INPUT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui clicar nessa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_INPUT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Clique {button} enviado ao centro do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, eventos "
                "e foco verificados, efeito interno não inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_MOUSE_MOVE_ANCHOR_PID = "_theos_expected_mouse_move_anchor_pid"
_EXPECTED_MOUSE_MOVE_ANCHOR_TITLE = "_theos_expected_mouse_move_anchor_title"
_EXPECTED_MOUSE_MOVE_ANCHOR_TARGET_TOKEN = (
    "_theos_expected_mouse_move_anchor_target_token"
)
_EXPECTED_MOUSE_MOVE_ANCHOR_NAME = "_theos_expected_mouse_move_anchor_name"


class MoveCursorWindowAnchorAction:
    name = "move_cursor_window_anchor"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        return ActionRisk.CONFIRM

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        anchor = request.arguments.get("anchor")
        anchor_spec = get_mouse_anchor_spec(anchor)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or anchor_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Movimento de cursor por âncora bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "MOVER CURSOR PARA ÂNCORA INTERNA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Âncora: {anchor} ({anchor_spec.label_pt})\n"
                f"Somente {format_mouse_anchor_allowlist_pt()} estão permitidas "
                "como âncoras nesta etapa.\n"
                f"Posição interna fixa: {anchor_spec.x_percent}% da largura e "
                f"{anchor_spec.y_percent}% da altura da área cliente da janela.\n"
                "Nenhum clique, wheel, tecla ou evento SendInput será enviado.\n"
                "Mover o cursor pode acionar apenas efeitos de hover definidos pelo "
                "aplicativo; o THE OS não inspeciona nem afirma esse efeito.\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, obterá localmente a área "
                "cliente, converterá sua origem para coordenadas de tela, calculará "
                "a âncora registrada, moverá e verificará o cursor nesse ponto e "
                "verificará novamente o foco. Coordenadas arbitrárias não são aceitas."
            ),
            execution_guard={
                _EXPECTED_MOUSE_MOVE_ANCHOR_PID: pid,
                _EXPECTED_MOUSE_MOVE_ANCHOR_TITLE: normalized_title,
                _EXPECTED_MOUSE_MOVE_ANCHOR_TARGET_TOKEN: target_token,
                _EXPECTED_MOUSE_MOVE_ANCHOR_NAME: anchor,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        anchor = request.arguments.get("anchor")
        anchor_spec = get_mouse_anchor_spec(anchor)
        expected_pid = request.arguments.get(_EXPECTED_MOUSE_MOVE_ANCHOR_PID)
        expected_title = request.arguments.get(_EXPECTED_MOUSE_MOVE_ANCHOR_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_MOUSE_MOVE_ANCHOR_TARGET_TOKEN
        )
        expected_anchor = request.arguments.get(_EXPECTED_MOUSE_MOVE_ANCHOR_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or anchor_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_anchor != anchor
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "O movimento de cursor por âncora não possui uma prévia local "
                    "aprovada."
                ),
                error_code="MOUSE_MOVE_ANCHOR_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.move_cursor_window_anchor(
                pid,
                title.strip(),
                target_token,
                anchor,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_MOVE_ANCHOR_BLOCKED": (
                    "A LYRA bloqueou movimento de cursor na própria janela.",
                    "SELF_WINDOW_MOUSE_MOVE_ANCHOR_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o movimento do cursor foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_MOVE_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED": (
                    "O Windows não confirmou a janela alvo antes do movimento.",
                    "MOUSE_MOVE_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_MOVE_ANCHOR_CLIENT_RECT_INVALID": (
                    "A área cliente da janela alvo não pôde ser validada.",
                    "MOUSE_MOVE_ANCHOR_CLIENT_RECT_INVALID",
                ),
                "MOUSE_MOVE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED": (
                    "A origem da área cliente não pôde ser convertida para a tela.",
                    "MOUSE_MOVE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED",
                ),
                "MOUSE_MOVE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor na âncora registrada.",
                    "MOUSE_MOVE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_MOVE_ANCHOR_NOT_ALLOWED": (
                    "Essa âncora não está permitida nesta etapa.",
                    "MOUSE_MOVE_ANCHOR_NOT_ALLOWED",
                ),
                "MOUSE_MOVE_ANCHOR_FOREGROUND_CHANGED": (
                    "O foco mudou durante o movimento do cursor.",
                    "MOUSE_MOVE_ANCHOR_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui mover o cursor para essa âncora.",
                evidence={"reason": reason},
                error_code="MOUSE_MOVE_ANCHOR_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui mover o cursor para essa âncora.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_MOVE_ANCHOR_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Cursor movido para a âncora {anchor} do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição e foco "
                "verificados, sem clique e sem inspeção de efeito de hover."
            ),
            evidence=evidence,
        )


_EXPECTED_MOUSE_ANCHOR_PID = "_theos_expected_mouse_anchor_pid"
_EXPECTED_MOUSE_ANCHOR_TITLE = "_theos_expected_mouse_anchor_title"
_EXPECTED_MOUSE_ANCHOR_TARGET_TOKEN = "_theos_expected_mouse_anchor_target_token"
_EXPECTED_MOUSE_ANCHOR_BUTTON = "_theos_expected_mouse_anchor_button"
_EXPECTED_MOUSE_ANCHOR_NAME = "_theos_expected_mouse_anchor_name"


class ClickWindowAnchorAction:
    name = "click_window_anchor"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        button_spec = get_mouse_button_spec(request.arguments.get("button"))
        if button_spec is None:
            return ActionRisk.CONFIRM
        return button_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        button = request.arguments.get("button")
        anchor = request.arguments.get("anchor")
        button_spec = get_mouse_button_spec(button)
        anchor_spec = get_mouse_anchor_spec(anchor)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or button_spec is None
            or anchor_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Clique por âncora bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "CLICAR ÂNCORA INTERNA DA JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Botão: {button}\n"
                f"Âncora: {anchor} ({anchor_spec.label_pt})\n"
                f"Somente {format_mouse_button_allowlist_pt()} estão permitidos "
                "como botões nesta etapa.\n"
                f"Somente {format_mouse_anchor_allowlist_pt()} estão permitidas "
                "como âncoras nesta etapa.\n"
                f"Posição interna fixa: {anchor_spec.x_percent}% da largura e "
                f"{anchor_spec.y_percent}% da altura da área cliente da janela.\n"
                f"Operação registrada: {button_spec.intent_pt} na âncora interna "
                "selecionada. O aplicativo pode interpretar o clique conforme o "
                "controle sob esse ponto; o THE OS não inspeciona semanticamente o "
                "efeito.\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, obterá localmente a área "
                "cliente, converterá sua origem para coordenadas de tela, calculará "
                "a âncora registrada, posicionará e verificará o cursor nesse ponto, "
                "enviará exatamente dois eventos de mouse e verificará novamente o "
                "foco. Coordenadas arbitrárias, bordas e barra de título não são "
                "alvos deste tool, e o efeito interno não é inspecionado."
            ),
            execution_guard={
                _EXPECTED_MOUSE_ANCHOR_PID: pid,
                _EXPECTED_MOUSE_ANCHOR_TITLE: normalized_title,
                _EXPECTED_MOUSE_ANCHOR_TARGET_TOKEN: target_token,
                _EXPECTED_MOUSE_ANCHOR_BUTTON: button,
                _EXPECTED_MOUSE_ANCHOR_NAME: anchor,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        button = request.arguments.get("button")
        anchor = request.arguments.get("anchor")
        button_spec = get_mouse_button_spec(button)
        anchor_spec = get_mouse_anchor_spec(anchor)
        expected_pid = request.arguments.get(_EXPECTED_MOUSE_ANCHOR_PID)
        expected_title = request.arguments.get(_EXPECTED_MOUSE_ANCHOR_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_MOUSE_ANCHOR_TARGET_TOKEN
        )
        expected_button = request.arguments.get(_EXPECTED_MOUSE_ANCHOR_BUTTON)
        expected_anchor = request.arguments.get(_EXPECTED_MOUSE_ANCHOR_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or button_spec is None
            or anchor_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_button != button
            or expected_anchor != anchor
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O clique por âncora não possui uma prévia local aprovada.",
                error_code="MOUSE_ANCHOR_CLICK_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.click_window_anchor(
                pid,
                title.strip(),
                target_token,
                button,
                anchor,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_ANCHOR_INPUT_BLOCKED": (
                    "A LYRA bloqueou clique por âncora na própria janela.",
                    "SELF_WINDOW_MOUSE_ANCHOR_INPUT_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o clique por âncora foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_ANCHOR_INPUT_TARGET_ACTIVATION_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; o clique por âncora não foi enviado."
                    ),
                    "MOUSE_ANCHOR_INPUT_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_ANCHOR_CLIENT_RECT_INVALID": (
                    "A área cliente da janela alvo não pôde ser validada.",
                    "MOUSE_ANCHOR_CLIENT_RECT_INVALID",
                ),
                "MOUSE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED": (
                    "A origem da área cliente não pôde ser convertida para a tela.",
                    "MOUSE_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED",
                ),
                "MOUSE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor na âncora registrada.",
                    "MOUSE_ANCHOR_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_ANCHOR_INPUT_NOT_ALLOWED": (
                    "Esse botão ou âncora não está permitido nesta etapa.",
                    "MOUSE_ANCHOR_INPUT_NOT_ALLOWED",
                ),
                "MOUSE_ANCHOR_INPUT_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio completo do clique por âncora.",
                    "MOUSE_ANCHOR_INPUT_NOT_ACCEPTED",
                ),
                "MOUSE_ANCHOR_INPUT_FOREGROUND_CHANGED": (
                    (
                        "O foco mudou durante o clique por âncora; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    "MOUSE_ANCHOR_INPUT_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui clicar na âncora dessa janela.",
                evidence={"reason": reason},
                error_code="MOUSE_ANCHOR_INPUT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui clicar na âncora dessa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_ANCHOR_INPUT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Clique {button} enviado à âncora {anchor} do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, eventos "
                "e foco verificados, efeito interno não inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_DOUBLE_CLICK_PID = "_theos_expected_double_click_pid"
_EXPECTED_DOUBLE_CLICK_TITLE = "_theos_expected_double_click_title"
_EXPECTED_DOUBLE_CLICK_TARGET_TOKEN = "_theos_expected_double_click_target_token"
_EXPECTED_DOUBLE_CLICK_GESTURE = "_theos_expected_double_click_gesture"


class DoubleClickWindowAction:
    name = "double_click_window"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        gesture_spec = get_mouse_gesture_spec(request.arguments.get("gesture"))
        if gesture_spec is None:
            return ActionRisk.CONFIRM
        return gesture_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        gesture_spec = get_mouse_gesture_spec(gesture)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or gesture_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Duplo clique bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "DUPLO CLIQUE NO CENTRO DA JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Gesto: {gesture} ({gesture_spec.label_pt})\n"
                "Posição: centro geométrico da janela exata no momento da execução.\n"
                "Sequência fixa: quatro eventos LEFT down/up/down/up.\n"
                f"{gesture_spec.preview_effect}\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, calculará localmente o centro "
                "da janela, posicionará e verificará o cursor nesse ponto, enviará "
                "exatamente quatro eventos de mouse e verificará novamente o foco. "
                "Botão, quantidade, intervalo e coordenadas arbitrários não são "
                "aceitos; o THE OS não afirma o efeito semântico do gesto."
            ),
            execution_guard={
                _EXPECTED_DOUBLE_CLICK_PID: pid,
                _EXPECTED_DOUBLE_CLICK_TITLE: normalized_title,
                _EXPECTED_DOUBLE_CLICK_TARGET_TOKEN: target_token,
                _EXPECTED_DOUBLE_CLICK_GESTURE: gesture,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        gesture_spec = get_mouse_gesture_spec(gesture)
        expected_pid = request.arguments.get(_EXPECTED_DOUBLE_CLICK_PID)
        expected_title = request.arguments.get(_EXPECTED_DOUBLE_CLICK_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_DOUBLE_CLICK_TARGET_TOKEN
        )
        expected_gesture = request.arguments.get(_EXPECTED_DOUBLE_CLICK_GESTURE)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or gesture_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_gesture != gesture
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O duplo clique não possui uma prévia local aprovada.",
                error_code="MOUSE_DOUBLE_CLICK_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.double_click_window_center(
                pid,
                title.strip(),
                target_token,
                gesture,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_DOUBLE_CLICK_BLOCKED": (
                    "A LYRA bloqueou duplo clique na própria janela.",
                    "SELF_WINDOW_MOUSE_DOUBLE_CLICK_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o duplo clique foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_DOUBLE_CLICK_TARGET_ACTIVATION_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; o gesto não foi enviado."
                    ),
                    "MOUSE_DOUBLE_CLICK_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_DOUBLE_CLICK_WINDOW_RECT_INVALID": (
                    "A geometria da janela alvo não pôde ser validada.",
                    "MOUSE_DOUBLE_CLICK_WINDOW_RECT_INVALID",
                ),
                "MOUSE_DOUBLE_CLICK_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor no centro da janela.",
                    "MOUSE_DOUBLE_CLICK_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_DOUBLE_CLICK_NOT_ALLOWED": (
                    "Esse gesto de mouse não está permitido nesta etapa.",
                    "MOUSE_DOUBLE_CLICK_NOT_ALLOWED",
                ),
                "MOUSE_DOUBLE_CLICK_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio completo dos quatro eventos.",
                    "MOUSE_DOUBLE_CLICK_NOT_ACCEPTED",
                ),
                "MOUSE_DOUBLE_CLICK_FOREGROUND_CHANGED": (
                    (
                        "O foco mudou durante o gesto; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    "MOUSE_DOUBLE_CLICK_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o duplo clique nessa janela.",
                evidence={"reason": reason},
                error_code="MOUSE_DOUBLE_CLICK_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o duplo clique nessa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_DOUBLE_CLICK_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Sequência {gesture} enviada ao centro do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, quatro eventos "
                "e foco verificados, reconhecimento semântico não inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_DOUBLE_CLICK_ANCHOR_PID = "_theos_expected_double_click_anchor_pid"
_EXPECTED_DOUBLE_CLICK_ANCHOR_TITLE = "_theos_expected_double_click_anchor_title"
_EXPECTED_DOUBLE_CLICK_ANCHOR_TARGET_TOKEN = (
    "_theos_expected_double_click_anchor_target_token"
)
_EXPECTED_DOUBLE_CLICK_ANCHOR_GESTURE = (
    "_theos_expected_double_click_anchor_gesture"
)
_EXPECTED_DOUBLE_CLICK_ANCHOR_NAME = "_theos_expected_double_click_anchor_name"


class DoubleClickWindowAnchorAction:
    name = "double_click_window_anchor"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        gesture_spec = get_mouse_gesture_spec(request.arguments.get("gesture"))
        if gesture_spec is None:
            return ActionRisk.CONFIRM
        return gesture_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        anchor = request.arguments.get("anchor")
        gesture_spec = get_mouse_gesture_spec(gesture)
        anchor_spec = get_mouse_anchor_spec(anchor)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or gesture_spec is None
            or anchor_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Duplo clique por âncora bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "DUPLO CLIQUE EM ÂNCORA INTERNA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Gesto: {gesture} ({gesture_spec.label_pt})\n"
                f"Âncora: {anchor} ({anchor_spec.label_pt})\n"
                f"Somente {format_mouse_anchor_allowlist_pt()} estão permitidas "
                "como âncoras nesta etapa.\n"
                f"Posição interna fixa: {anchor_spec.x_percent}% da largura e "
                f"{anchor_spec.y_percent}% da altura da área cliente da janela.\n"
                "Sequência fixa: quatro eventos LEFT down/up/down/up.\n"
                "O aplicativo pode interpretar essa sequência conforme o controle sob "
                "a âncora selecionada; o THE OS verifica apenas posição, eventos e "
                "foco, sem afirmar reconhecimento semântico de duplo clique.\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, obterá a área cliente, "
                "converterá sua origem para coordenadas de tela, calculará a âncora "
                "registrada, posicionará e verificará o cursor, enviará exatamente "
                "quatro eventos e verificará novamente o foco. Coordenadas, quantidade "
                "e intervalo arbitrários não são aceitos."
            ),
            execution_guard={
                _EXPECTED_DOUBLE_CLICK_ANCHOR_PID: pid,
                _EXPECTED_DOUBLE_CLICK_ANCHOR_TITLE: normalized_title,
                _EXPECTED_DOUBLE_CLICK_ANCHOR_TARGET_TOKEN: target_token,
                _EXPECTED_DOUBLE_CLICK_ANCHOR_GESTURE: gesture,
                _EXPECTED_DOUBLE_CLICK_ANCHOR_NAME: anchor,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        anchor = request.arguments.get("anchor")
        gesture_spec = get_mouse_gesture_spec(gesture)
        anchor_spec = get_mouse_anchor_spec(anchor)
        expected_pid = request.arguments.get(_EXPECTED_DOUBLE_CLICK_ANCHOR_PID)
        expected_title = request.arguments.get(_EXPECTED_DOUBLE_CLICK_ANCHOR_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_DOUBLE_CLICK_ANCHOR_TARGET_TOKEN
        )
        expected_gesture = request.arguments.get(
            _EXPECTED_DOUBLE_CLICK_ANCHOR_GESTURE
        )
        expected_anchor = request.arguments.get(_EXPECTED_DOUBLE_CLICK_ANCHOR_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or gesture_spec is None
            or anchor_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_gesture != gesture
            or expected_anchor != anchor
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O duplo clique por âncora não possui prévia local aprovada.",
                error_code="MOUSE_DOUBLE_CLICK_ANCHOR_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.double_click_window_anchor(
                pid,
                title.strip(),
                target_token,
                gesture,
                anchor,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_DOUBLE_CLICK_ANCHOR_BLOCKED": (
                    "A LYRA bloqueou duplo clique por âncora na própria janela.",
                    "SELF_WINDOW_MOUSE_DOUBLE_CLICK_ANCHOR_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o duplo clique por âncora foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela alvo em primeiro plano; "
                        "o gesto não foi enviado."
                    ),
                    "MOUSE_DOUBLE_CLICK_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_RECT_INVALID": (
                    "A área cliente da janela alvo não pôde ser validada.",
                    "MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_RECT_INVALID",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED": (
                    "A origem da área cliente não pôde ser convertida para a tela.",
                    "MOUSE_DOUBLE_CLICK_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor na âncora registrada.",
                    "MOUSE_DOUBLE_CLICK_ANCHOR_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ALLOWED": (
                    "Esse gesto ou âncora não está permitido nesta etapa.",
                    "MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ALLOWED",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio completo dos quatro eventos.",
                    "MOUSE_DOUBLE_CLICK_ANCHOR_NOT_ACCEPTED",
                ),
                "MOUSE_DOUBLE_CLICK_ANCHOR_FOREGROUND_CHANGED": (
                    (
                        "O foco mudou durante o gesto; não posso confirmar "
                        "que os eventos permaneceram no alvo."
                    ),
                    "MOUSE_DOUBLE_CLICK_ANCHOR_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o duplo clique nessa âncora.",
                evidence={"reason": reason},
                error_code="MOUSE_DOUBLE_CLICK_ANCHOR_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui enviar o duplo clique nessa âncora.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_DOUBLE_CLICK_ANCHOR_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Sequência {gesture} enviada à âncora {anchor} do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, quatro eventos "
                "e foco verificados, reconhecimento semântico não inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_DRAG_PID = "_theos_expected_drag_pid"
_EXPECTED_DRAG_TITLE = "_theos_expected_drag_title"
_EXPECTED_DRAG_TARGET_TOKEN = "_theos_expected_drag_target_token"
_EXPECTED_DRAG_GESTURE = "_theos_expected_drag_gesture"
_EXPECTED_DRAG_SOURCE_ANCHOR = "_theos_expected_drag_source_anchor"
_EXPECTED_DRAG_TARGET_ANCHOR = "_theos_expected_drag_target_anchor"


class DragWindowAnchorAction:
    name = "drag_window_anchor"
    risk = ActionRisk.DESTRUCTIVE

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        drag_spec = get_mouse_drag_spec(request.arguments.get("gesture"))
        if drag_spec is None:
            return ActionRisk.DESTRUCTIVE
        return drag_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        source_anchor = request.arguments.get("source_anchor")
        target_anchor = request.arguments.get("target_anchor")
        drag_spec = get_mouse_drag_spec(gesture)
        source_spec = get_mouse_anchor_spec(source_anchor)
        target_spec = get_mouse_anchor_spec(target_anchor)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or drag_spec is None
            or source_spec is None
            or target_spec is None
            or source_anchor == target_anchor
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Arrasto por âncoras bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "ARRASTAR ENTRE ÂNCORAS INTERNAS\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Gesto: {gesture} ({drag_spec.label_pt})\n"
                f"Origem: {source_anchor} ({source_spec.label_pt}) — "
                f"{source_spec.x_percent}% da largura e "
                f"{source_spec.y_percent}% da altura da área cliente.\n"
                f"Destino: {target_anchor} ({target_spec.label_pt}) — "
                f"{target_spec.x_percent}% da largura e "
                f"{target_spec.y_percent}% da altura da área cliente.\n"
                f"Somente {format_mouse_anchor_allowlist_pt()} estão permitidas "
                "como origem ou destino; origem e destino devem ser diferentes.\n"
                "Sequência fixa: posicionar origem, LEFTDOWN, mover para destino, "
                "LEFTUP.\n"
                f"{drag_spec.preview_effect}\n"
                "Após a confirmação, o THE OS reativará a janela exata, obterá "
                "localmente a área cliente, converterá sua origem para coordenadas de "
                "tela, calculará e verificará as duas âncoras, enviará exatamente um "
                "LEFTDOWN e um LEFTUP e verificará a continuidade de foco. Coordenadas, "
                "trajeto, duração e botão arbitrários não são aceitos."
            ),
            execution_guard={
                _EXPECTED_DRAG_PID: pid,
                _EXPECTED_DRAG_TITLE: normalized_title,
                _EXPECTED_DRAG_TARGET_TOKEN: target_token,
                _EXPECTED_DRAG_GESTURE: gesture,
                _EXPECTED_DRAG_SOURCE_ANCHOR: source_anchor,
                _EXPECTED_DRAG_TARGET_ANCHOR: target_anchor,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        gesture = request.arguments.get("gesture")
        source_anchor = request.arguments.get("source_anchor")
        target_anchor = request.arguments.get("target_anchor")
        drag_spec = get_mouse_drag_spec(gesture)
        source_spec = get_mouse_anchor_spec(source_anchor)
        target_spec = get_mouse_anchor_spec(target_anchor)
        expected_pid = request.arguments.get(_EXPECTED_DRAG_PID)
        expected_title = request.arguments.get(_EXPECTED_DRAG_TITLE)
        expected_target_token = request.arguments.get(_EXPECTED_DRAG_TARGET_TOKEN)
        expected_gesture = request.arguments.get(_EXPECTED_DRAG_GESTURE)
        expected_source_anchor = request.arguments.get(_EXPECTED_DRAG_SOURCE_ANCHOR)
        expected_target_anchor = request.arguments.get(_EXPECTED_DRAG_TARGET_ANCHOR)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or drag_spec is None
            or source_spec is None
            or target_spec is None
            or source_anchor == target_anchor
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_gesture != gesture
            or expected_source_anchor != source_anchor
            or expected_target_anchor != target_anchor
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="O arrasto por âncoras não possui uma prévia local aprovada.",
                error_code="MOUSE_DRAG_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.drag_window_anchor(
                pid,
                title.strip(),
                target_token,
                gesture,
                source_anchor,
                target_anchor,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_DRAG_BLOCKED": (
                    "A LYRA bloqueou arrasto na própria janela.",
                    "SELF_WINDOW_MOUSE_DRAG_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    "Mais de uma janela correspondeu ao alvo; o arrasto foi bloqueado.",
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_DRAG_TARGET_ACTIVATION_NOT_VERIFIED": (
                    "O Windows não confirmou a janela alvo antes do arrasto.",
                    "MOUSE_DRAG_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_DRAG_CLIENT_RECT_INVALID": (
                    "A área cliente da janela alvo não pôde ser validada.",
                    "MOUSE_DRAG_CLIENT_RECT_INVALID",
                ),
                "MOUSE_DRAG_CLIENT_ORIGIN_NOT_VERIFIED": (
                    "A origem da área cliente não pôde ser convertida para a tela.",
                    "MOUSE_DRAG_CLIENT_ORIGIN_NOT_VERIFIED",
                ),
                "MOUSE_DRAG_SOURCE_CURSOR_NOT_VERIFIED": (
                    "O cursor não pôde ser confirmado na âncora de origem.",
                    "MOUSE_DRAG_SOURCE_CURSOR_NOT_VERIFIED",
                ),
                "MOUSE_DRAG_TARGET_CURSOR_NOT_VERIFIED": (
                    "O cursor não pôde ser confirmado na âncora de destino.",
                    "MOUSE_DRAG_TARGET_CURSOR_NOT_VERIFIED",
                ),
                "MOUSE_DRAG_NOT_ALLOWED": (
                    "Esse gesto ou par de âncoras não está permitido.",
                    "MOUSE_DRAG_NOT_ALLOWED",
                ),
                "MOUSE_DRAG_BUTTON_DOWN_NOT_ACCEPTED": (
                    "O Windows não confirmou o LEFTDOWN do arrasto.",
                    "MOUSE_DRAG_BUTTON_DOWN_NOT_ACCEPTED",
                ),
                "MOUSE_DRAG_BUTTON_UP_NOT_ACCEPTED": (
                    "O Windows não confirmou o LEFTUP do arrasto.",
                    "MOUSE_DRAG_BUTTON_UP_NOT_ACCEPTED",
                ),
                "MOUSE_DRAG_FOREGROUND_CHANGED": (
                    "O foco mudou durante o arrasto; o resultado não é confiável.",
                    "MOUSE_DRAG_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui executar o arrasto limitado.",
                evidence={"reason": reason},
                error_code="MOUSE_DRAG_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui executar o arrasto limitado.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_DRAG_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Arrasto {gesture} enviado de {source_anchor} para {target_anchor} "
                f"no alvo: {evidence['title']} (PID {evidence['pid']}); origem, "
                "destino, LEFTDOWN/LEFTUP e foco verificados, efeito interno não "
                "inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_SCROLL_ANCHOR_PID = "_theos_expected_scroll_anchor_pid"
_EXPECTED_SCROLL_ANCHOR_TITLE = "_theos_expected_scroll_anchor_title"
_EXPECTED_SCROLL_ANCHOR_TARGET_TOKEN = "_theos_expected_scroll_anchor_target_token"
_EXPECTED_SCROLL_ANCHOR_DIRECTION = "_theos_expected_scroll_anchor_direction"
_EXPECTED_SCROLL_ANCHOR_NAME = "_theos_expected_scroll_anchor_name"


class ScrollWindowAnchorAction:
    name = "scroll_window_anchor"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        scroll_spec = get_mouse_scroll_spec(request.arguments.get("direction"))
        if scroll_spec is None:
            return ActionRisk.CONFIRM
        return scroll_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        direction = request.arguments.get("direction")
        anchor = request.arguments.get("anchor")
        scroll_spec = get_mouse_scroll_spec(direction)
        anchor_spec = get_mouse_anchor_spec(anchor)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or scroll_spec is None
            or anchor_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Rolagem por âncora bloqueada antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "ROLAR EM ÂNCORA INTERNA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Direção: {direction} ({scroll_spec.label_pt})\n"
                f"Âncora: {anchor} ({anchor_spec.label_pt})\n"
                f"Somente {format_mouse_scroll_allowlist_pt()} estão permitidos "
                "como direções nesta etapa.\n"
                f"Somente {format_mouse_anchor_allowlist_pt()} estão permitidas "
                "como âncoras nesta etapa.\n"
                f"Posição interna fixa: {anchor_spec.x_percent}% da largura e "
                f"{anchor_spec.y_percent}% da altura da área cliente da janela.\n"
                "Quantidade: uma unidade fixa de wheel por execução.\n"
                "O aplicativo pode interpretar a rolagem conforme o controle sob a "
                "âncora selecionada; o THE OS verifica apenas geometria, envio e foco, "
                "sem inspecionar semanticamente o resultado.\n"
                "Após a confirmação, o THE OS reativará a janela exata, obterá "
                "localmente a área cliente, converterá sua origem para coordenadas de "
                "tela, calculará e verificará a âncora registrada, enviará exatamente "
                "um evento de wheel e verificará novamente o foco. Quantidade, "
                "horizontal e coordenadas arbitrárias não são aceitos."
            ),
            execution_guard={
                _EXPECTED_SCROLL_ANCHOR_PID: pid,
                _EXPECTED_SCROLL_ANCHOR_TITLE: normalized_title,
                _EXPECTED_SCROLL_ANCHOR_TARGET_TOKEN: target_token,
                _EXPECTED_SCROLL_ANCHOR_DIRECTION: direction,
                _EXPECTED_SCROLL_ANCHOR_NAME: anchor,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        direction = request.arguments.get("direction")
        anchor = request.arguments.get("anchor")
        scroll_spec = get_mouse_scroll_spec(direction)
        anchor_spec = get_mouse_anchor_spec(anchor)
        expected_pid = request.arguments.get(_EXPECTED_SCROLL_ANCHOR_PID)
        expected_title = request.arguments.get(_EXPECTED_SCROLL_ANCHOR_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_SCROLL_ANCHOR_TARGET_TOKEN
        )
        expected_direction = request.arguments.get(_EXPECTED_SCROLL_ANCHOR_DIRECTION)
        expected_anchor = request.arguments.get(_EXPECTED_SCROLL_ANCHOR_NAME)

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or scroll_spec is None
            or anchor_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_direction != direction
            or expected_anchor != anchor
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A rolagem por âncora não possui uma prévia local aprovada.",
                error_code="MOUSE_SCROLL_ANCHOR_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.scroll_window_anchor(
                pid,
                title.strip(),
                target_token,
                direction,
                anchor,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_SCROLL_ANCHOR_BLOCKED": (
                    "A LYRA bloqueou rolagem por âncora na própria janela.",
                    "SELF_WINDOW_MOUSE_SCROLL_ANCHOR_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    "Mais de uma janela correspondeu ao alvo; a rolagem foi bloqueada.",
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_SCROLL_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED": (
                    "O Windows não confirmou a janela alvo antes da rolagem.",
                    "MOUSE_SCROLL_ANCHOR_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_SCROLL_ANCHOR_CLIENT_RECT_INVALID": (
                    "A área cliente da janela alvo não pôde ser validada.",
                    "MOUSE_SCROLL_ANCHOR_CLIENT_RECT_INVALID",
                ),
                "MOUSE_SCROLL_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED": (
                    "A origem da área cliente não pôde ser convertida para a tela.",
                    "MOUSE_SCROLL_ANCHOR_CLIENT_ORIGIN_NOT_VERIFIED",
                ),
                "MOUSE_SCROLL_ANCHOR_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor na âncora registrada.",
                    "MOUSE_SCROLL_ANCHOR_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_SCROLL_ANCHOR_NOT_ALLOWED": (
                    "Essa direção ou âncora não está permitida nesta etapa.",
                    "MOUSE_SCROLL_ANCHOR_NOT_ALLOWED",
                ),
                "MOUSE_SCROLL_ANCHOR_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio da rolagem por âncora.",
                    "MOUSE_SCROLL_ANCHOR_NOT_ACCEPTED",
                ),
                "MOUSE_SCROLL_ANCHOR_FOREGROUND_CHANGED": (
                    "O foco mudou durante a rolagem; o resultado não é confiável.",
                    "MOUSE_SCROLL_ANCHOR_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui executar a rolagem por âncora.",
                evidence={"reason": reason},
                error_code="MOUSE_SCROLL_ANCHOR_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui executar a rolagem por âncora.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_SCROLL_ANCHOR_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Rolagem {direction} enviada à âncora {anchor} do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, wheel e foco "
                "verificados, efeito interno não inspecionado."
            ),
            evidence=evidence,
        )


_EXPECTED_SCROLL_PID = "_theos_expected_scroll_pid"
_EXPECTED_SCROLL_TITLE = "_theos_expected_scroll_title"
_EXPECTED_SCROLL_TARGET_TOKEN = "_theos_expected_scroll_target_token"
_EXPECTED_SCROLL_DIRECTION = "_theos_expected_scroll_direction"


class ScrollWindowAction:
    name = "scroll_window"
    risk = ActionRisk.CONFIRM

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        scroll_spec = get_mouse_scroll_spec(
            request.arguments.get("direction")
        )
        if scroll_spec is None:
            return ActionRisk.CONFIRM
        return scroll_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        direction = request.arguments.get("direction")
        scroll_spec = get_mouse_scroll_spec(direction)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or scroll_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Rolagem de mouse bloqueada antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        return ConfirmationPreview(
            allowed=True,
            text=(
                "ROLAR JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Direção: {direction}\n"
                f"Somente {format_mouse_scroll_allowlist_pt()} estão permitidos "
                "nesta etapa.\n"
                "Posição: centro geométrico da janela exata no momento da execução.\n"
                "Quantidade: uma unidade fixa de wheel por execução.\n"
                f"{scroll_spec.preview_effect}\n"
                "Após a confirmação, o THE OS reativará somente a janela exata "
                "aprovada, verificará o primeiro plano, calculará localmente o centro "
                "da janela, posicionará e verificará o cursor nesse ponto, enviará "
                "exatamente um evento de wheel e verificará novamente o foco. "
                "Quantidade e coordenadas arbitrárias não são aceitas e o efeito "
                "interno não é inspecionado."
            ),
            execution_guard={
                _EXPECTED_SCROLL_PID: pid,
                _EXPECTED_SCROLL_TITLE: normalized_title,
                _EXPECTED_SCROLL_TARGET_TOKEN: target_token,
                _EXPECTED_SCROLL_DIRECTION: direction,
            },
        )

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        direction = request.arguments.get("direction")
        scroll_spec = get_mouse_scroll_spec(direction)
        expected_pid = request.arguments.get(_EXPECTED_SCROLL_PID)
        expected_title = request.arguments.get(_EXPECTED_SCROLL_TITLE)
        expected_target_token = request.arguments.get(
            _EXPECTED_SCROLL_TARGET_TOKEN
        )
        expected_direction = request.arguments.get(
            _EXPECTED_SCROLL_DIRECTION
        )

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or scroll_spec is None
            or expected_pid != pid
            or expected_title != title.strip()
            or expected_target_token != target_token
            or expected_direction != direction
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="A rolagem de mouse não possui uma prévia local aprovada.",
                error_code="MOUSE_SCROLL_PREVIEW_REQUIRED",
            )

        try:
            evidence = self._windows.scroll_window_center(
                pid,
                title.strip(),
                target_token,
                direction,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_MOUSE_SCROLL_BLOCKED": (
                    "A LYRA bloqueou rolagem de mouse na própria janela.",
                    "SELF_WINDOW_MOUSE_SCROLL_BLOCKED",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "a rolagem foi bloqueada."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "MOUSE_SCROLL_TARGET_ACTIVATION_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela alvo em primeiro plano "
                        "após a confirmação; a rolagem não foi enviada."
                    ),
                    "MOUSE_SCROLL_TARGET_ACTIVATION_NOT_VERIFIED",
                ),
                "MOUSE_SCROLL_WINDOW_RECT_INVALID": (
                    "A geometria da janela alvo não pôde ser validada.",
                    "MOUSE_SCROLL_WINDOW_RECT_INVALID",
                ),
                "MOUSE_SCROLL_CURSOR_POSITION_NOT_VERIFIED": (
                    "O Windows não confirmou o cursor no centro da janela.",
                    "MOUSE_SCROLL_CURSOR_POSITION_NOT_VERIFIED",
                ),
                "MOUSE_SCROLL_NOT_ALLOWED": (
                    "Essa direção de rolagem não está permitida nesta etapa.",
                    "MOUSE_SCROLL_NOT_ALLOWED",
                ),
                "MOUSE_SCROLL_NOT_ACCEPTED": (
                    "O Windows não confirmou o envio da rolagem.",
                    "MOUSE_SCROLL_NOT_ACCEPTED",
                ),
                "MOUSE_SCROLL_FOREGROUND_CHANGED": (
                    (
                        "O foco mudou durante a rolagem; não posso confirmar "
                        "que o evento permaneceu no alvo."
                    ),
                    "MOUSE_SCROLL_FOREGROUND_CHANGED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui rolar essa janela.",
                evidence={"reason": reason},
                error_code="MOUSE_SCROLL_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui rolar essa janela.",
                evidence={"exception": type(exc).__name__},
                error_code="MOUSE_SCROLL_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Rolagem {direction} enviada ao centro do alvo: "
                f"{evidence['title']} (PID {evidence['pid']}); posição, evento "
                "e foco verificados, efeito interno não inspecionado."
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
        key_spec = get_window_key_spec(request.arguments.get("key"))
        if key_spec is None:
            return ActionRisk.CONFIRM
        return key_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        key = request.arguments.get("key")
        key_spec = get_window_key_spec(key)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or key_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text="Entrada de tecla bloqueada antes da confirmação: argumentos inválidos.",
            )

        normalized_title = title.strip()
        key_effect = key_spec.preview_effect
        return ConfirmationPreview(
            allowed=True,
            text=(
                "PRESSIONAR TECLA EM JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Tecla: {key}\n"
                f"Somente {format_window_key_allowlist_pt()} estão permitidas nesta etapa.\n"
                f"{key_effect}\n"
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
        key_spec = get_window_key_spec(key)
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
            or key_spec is None
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
        shortcut_spec = get_window_shortcut_spec(
            request.arguments.get("shortcut")
        )
        if shortcut_spec is None:
            return ActionRisk.CONFIRM
        return shortcut_spec.risk

    @staticmethod
    def confirmation_preview(request: ActionRequest) -> ConfirmationPreview:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        shortcut = request.arguments.get("shortcut")
        shortcut_spec = get_window_shortcut_spec(shortcut)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or shortcut_spec is None
        ):
            return ConfirmationPreview(
                allowed=False,
                text=(
                    "Atalho de teclado bloqueado antes da confirmação: "
                    "argumentos inválidos."
                ),
            )

        normalized_title = title.strip()
        shortcut_label = shortcut_spec.label
        shortcut_effect = shortcut_spec.preview_effect
        return ConfirmationPreview(
            allowed=True,
            text=(
                "PRESSIONAR ATALHO EM JANELA\n"
                f"Janela: {normalized_title}\n"
                f"PID: {pid}\n"
                f"Alvo opaco: {target_token[:12]}...\n"
                f"Atalho: {shortcut_label}\n"
                f"Somente {format_window_shortcut_allowlist_pt()} estão permitidos nesta etapa. "
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
        shortcut_spec = get_window_shortcut_spec(shortcut)
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
            or shortcut_spec is None
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

        shortcut_label = shortcut_spec.label
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


class PlaceWindowAction:
    name = "place_window"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        placement_spec = get_window_placement_spec(
            request.arguments.get("placement")
        )
        if placement_spec is None:
            return ActionRisk.NORMAL
        return placement_spec.risk

    def execute(self, request: ActionRequest) -> ActionResult:
        pid = request.arguments.get("pid")
        title = request.arguments.get("title")
        target_token = request.arguments.get("target_token")
        placement = request.arguments.get("placement")
        placement_spec = get_window_placement_spec(placement)
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(title, str)
            or not title.strip()
            or not is_window_target_token(target_token)
            or placement_spec is None
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "PID, título, alvo opaco e layout registrado da janela "
                    "são obrigatórios."
                ),
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.place_window(
                pid,
                title.strip(),
                target_token,
                placement,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_PLACEMENT_BLOCKED": (
                    "A LYRA bloqueou o reposicionamento da própria janela.",
                    "SELF_WINDOW_PLACEMENT_BLOCKED",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "O identificador opaco da janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "WINDOW_TARGET_NOT_FOUND": (
                    "Não encontrei essa janela visível exata.",
                    "WINDOW_TARGET_NOT_FOUND",
                ),
                "WINDOW_TARGET_AMBIGUOUS": (
                    (
                        "Mais de uma janela correspondeu ao alvo opaco; "
                        "o layout foi bloqueado."
                    ),
                    "WINDOW_TARGET_AMBIGUOUS",
                ),
                "WINDOW_PLACEMENT_NOT_ALLOWED": (
                    "Esse layout de janela não está permitido.",
                    "WINDOW_PLACEMENT_NOT_ALLOWED",
                ),
                "WINDOW_PLACEMENT_RESTORE_NOT_VERIFIED": (
                    (
                        "O Windows não confirmou a janela em estado normal "
                        "antes de aplicar o layout."
                    ),
                    "WINDOW_PLACEMENT_RESTORE_NOT_VERIFIED",
                ),
                "WINDOW_PLACEMENT_MONITOR_NOT_FOUND": (
                    "Não foi possível identificar o monitor atual da janela.",
                    "WINDOW_PLACEMENT_MONITOR_NOT_FOUND",
                ),
                "WINDOW_PLACEMENT_MONITOR_INFO_FAILED": (
                    "Não foi possível obter a área útil do monitor atual.",
                    "WINDOW_PLACEMENT_MONITOR_INFO_FAILED",
                ),
                "WINDOW_PLACEMENT_WORK_AREA_INVALID": (
                    "A área útil do monitor atual é inválida.",
                    "WINDOW_PLACEMENT_WORK_AREA_INVALID",
                ),
                "WINDOW_PLACEMENT_MOVE_NOT_ACCEPTED": (
                    "O Windows não aceitou o reposicionamento da janela.",
                    "WINDOW_PLACEMENT_MOVE_NOT_ACCEPTED",
                ),
                "WINDOW_PLACEMENT_NOT_VERIFIED": (
                    "O Windows não confirmou o retângulo final exato solicitado.",
                    "WINDOW_PLACEMENT_NOT_VERIFIED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar esse layout à janela.",
                evidence={"reason": reason},
                error_code="WINDOW_PLACEMENT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar esse layout à janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_PLACEMENT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata posicionada em {placement} "
                f"({placement_spec.label_pt}) e retângulo verificado: "
                f"{evidence['title']} (PID {evidence['pid']})."
            ),
            evidence=evidence,
        )




class PlaceWindowPairAction:
    name = "place_window_pair"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        layout_spec = get_window_pair_layout_spec(
            request.arguments.get("arrangement")
        )
        if layout_spec is None:
            return ActionRisk.NORMAL
        return layout_spec.risk

    def execute(self, request: ActionRequest) -> ActionResult:
        first_target_token = request.arguments.get("first_target_token")
        second_target_token = request.arguments.get("second_target_token")
        arrangement = request.arguments.get("arrangement")
        layout_spec = get_window_pair_layout_spec(arrangement)

        if (
            not is_window_target_token(first_target_token)
            or not is_window_target_token(second_target_token)
            or first_target_token == second_target_token
            or layout_spec is None
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "Dois tokens opacos distintos e um arranjo registrado "
                    "são obrigatórios."
                ),
                error_code="ACTION_VALIDATION_FAILED",
            )

        try:
            evidence = self._windows.place_window_pair(
                first_target_token,
                second_target_token,
                arrangement,
            )
        except RuntimeError as exc:
            reason = str(exc)
            error_map = {
                "SELF_WINDOW_PAIR_PLACEMENT_BLOCKED": (
                    "A LYRA bloqueou o reposicionamento da própria janela.",
                    "SELF_WINDOW_PAIR_PLACEMENT_BLOCKED",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "Um dos identificadores opacos de janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "WINDOW_PAIR_SAME_TARGET": (
                    "As duas posições precisam apontar para janelas distintas.",
                    "WINDOW_PAIR_SAME_TARGET",
                ),
                "WINDOW_PAIR_LAYOUT_NOT_ALLOWED": (
                    "Esse arranjo de duas janelas não está permitido.",
                    "WINDOW_PAIR_LAYOUT_NOT_ALLOWED",
                ),
                "WINDOW_PAIR_FIRST_TARGET_NOT_FOUND": (
                    "Não encontrei a primeira janela visível exata pelo token opaco.",
                    "WINDOW_PAIR_FIRST_TARGET_NOT_FOUND",
                ),
                "WINDOW_PAIR_FIRST_TARGET_AMBIGUOUS": (
                    "O primeiro token opaco não resolveu uma única janela.",
                    "WINDOW_PAIR_FIRST_TARGET_AMBIGUOUS",
                ),
                "WINDOW_PAIR_SECOND_TARGET_NOT_FOUND": (
                    "Não encontrei a segunda janela visível exata pelo token opaco.",
                    "WINDOW_PAIR_SECOND_TARGET_NOT_FOUND",
                ),
                "WINDOW_PAIR_SECOND_TARGET_AMBIGUOUS": (
                    "O segundo token opaco não resolveu uma única janela.",
                    "WINDOW_PAIR_SECOND_TARGET_AMBIGUOUS",
                ),
                "WINDOW_PAIR_VISUAL_FRAME_NOT_FOUND": (
                    "Não encontrei uma moldura visual operável e única para uma das janelas.",
                    "WINDOW_PAIR_VISUAL_FRAME_NOT_FOUND",
                ),
                "WINDOW_PAIR_VISUAL_FRAME_AMBIGUOUS": (
                    "Mais de uma moldura visual operável correspondeu à janela hospedada.",
                    "WINDOW_PAIR_VISUAL_FRAME_AMBIGUOUS",
                ),
                "WINDOW_PAIR_NORMAL_STATE_REQUIRED": (
                    "As duas janelas precisam estar em estado normal antes do arranjo.",
                    "WINDOW_PAIR_NORMAL_STATE_REQUIRED",
                ),
                "WINDOW_PAIR_ORIGINAL_RECT_FAILED": (
                    "Não foi possível guardar os retângulos originais das duas janelas.",
                    "WINDOW_PAIR_ORIGINAL_RECT_FAILED",
                ),
                "WINDOW_PAIR_MONITOR_NOT_FOUND": (
                    "Não foi possível identificar o monitor das duas janelas.",
                    "WINDOW_PAIR_MONITOR_NOT_FOUND",
                ),
                "WINDOW_PAIR_MONITOR_MISMATCH": (
                    "As duas janelas precisam estar no mesmo monitor para este arranjo.",
                    "WINDOW_PAIR_MONITOR_MISMATCH",
                ),
                "WINDOW_PAIR_MONITOR_INFO_FAILED": (
                    "Não foi possível obter a área útil do monitor compartilhado.",
                    "WINDOW_PAIR_MONITOR_INFO_FAILED",
                ),
                "WINDOW_PAIR_WORK_AREA_INVALID": (
                    "A área útil do monitor compartilhado é inválida.",
                    "WINDOW_PAIR_WORK_AREA_INVALID",
                ),
                "WINDOW_PAIR_MOVE_NOT_ACCEPTED": (
                    "O Windows não aceitou uma das movimentações do arranjo.",
                    "WINDOW_PAIR_MOVE_NOT_ACCEPTED",
                ),
                "WINDOW_PAIR_NOT_VERIFIED": (
                    "O Windows não confirmou os dois retângulos finais exatos.",
                    "WINDOW_PAIR_NOT_VERIFIED",
                ),
                "WINDOW_PAIR_ROLLBACK_FAILED": (
                    "O arranjo falhou e o rollback exato das janelas também não foi verificado.",
                    "WINDOW_PAIR_ROLLBACK_FAILED",
                ),
            }
            mapped = error_map.get(reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar o arranjo de duas janelas.",
                evidence={"reason": reason},
                error_code="WINDOW_PAIR_PLACEMENT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar o arranjo de duas janelas.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_PAIR_PLACEMENT_FAILED",
            )

        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Duas janelas organizadas em {arrangement} "
                f"({layout_spec.label_pt}) e ambos os retângulos verificados: "
                f"{evidence['first_title']} (PID {evidence['first_pid']}) + "
                f"{evidence['second_title']} (PID {evidence['second_pid']})."
            ),
            evidence=evidence,
        )


class PlaceWindowSetAction:
    name = "place_window_set"
    risk = ActionRisk.NORMAL

    def __init__(self, windows: WindowsDesktopWindowAdapter) -> None:
        self._windows = windows

    @staticmethod
    def risk_for(request: ActionRequest) -> ActionRisk:
        layout_spec = get_window_set_layout_spec(
            request.arguments.get("arrangement")
        )
        if layout_spec is None:
            return ActionRisk.NORMAL
        return layout_spec.risk

    def execute(self, request: ActionRequest) -> ActionResult:
        raw_tokens = request.arguments.get("target_tokens")
        arrangement = request.arguments.get("arrangement")
        layout_spec = get_window_set_layout_spec(arrangement)

        if not isinstance(raw_tokens, (list, tuple)):
            tokens: tuple[object, ...] = ()
        else:
            tokens = tuple(raw_tokens)

        if (
            layout_spec is None
            or len(tokens) not in (3, 4)
            or len(tokens) != layout_spec.target_count
            or any(not is_window_target_token(token) for token in tokens)
            or len(set(tokens)) != len(tokens)
        ):
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message=(
                    "São obrigatórios 3 ou 4 tokens opacos distintos compatíveis "
                    "com um arranjo multi-janela registrado."
                ),
                error_code="ACTION_VALIDATION_FAILED",
            )

        target_tokens = tuple(str(token) for token in tokens)

        try:
            evidence = self._windows.place_window_set(
                target_tokens,
                arrangement,
            )
        except RuntimeError as exc:
            reason = str(exc)
            base_reason = reason.split(":", 1)[0]
            error_map = {
                "SELF_WINDOW_SET_PLACEMENT_BLOCKED": (
                    "A LYRA bloqueou o reposicionamento da própria janela.",
                    "SELF_WINDOW_SET_PLACEMENT_BLOCKED",
                ),
                "WINDOW_TARGET_TOKEN_INVALID": (
                    "Um dos identificadores opacos de janela é inválido.",
                    "WINDOW_TARGET_TOKEN_INVALID",
                ),
                "WINDOW_SET_DUPLICATE_TARGET": (
                    "Os alvos do conjunto precisam ser distintos.",
                    "WINDOW_SET_DUPLICATE_TARGET",
                ),
                "WINDOW_SET_TARGET_COUNT_MISMATCH": (
                    "A quantidade de janelas não corresponde ao arranjo registrado.",
                    "WINDOW_SET_TARGET_COUNT_MISMATCH",
                ),
                "WINDOW_SET_LAYOUT_NOT_ALLOWED": (
                    "Esse arranjo multi-janela não está permitido.",
                    "WINDOW_SET_LAYOUT_NOT_ALLOWED",
                ),
                "WINDOW_SET_TARGET_NOT_FOUND": (
                    "Não encontrei uma das janelas visíveis exatas pelo token opaco.",
                    "WINDOW_SET_TARGET_NOT_FOUND",
                ),
                "WINDOW_SET_TARGET_AMBIGUOUS": (
                    "Um token opaco não resolveu uma única janela.",
                    "WINDOW_SET_TARGET_AMBIGUOUS",
                ),
                "WINDOW_SET_VISUAL_FRAME_NOT_FOUND": (
                    "Não encontrei uma moldura visual operável e única para uma janela hospedada.",
                    "WINDOW_SET_VISUAL_FRAME_NOT_FOUND",
                ),
                "WINDOW_SET_VISUAL_FRAME_AMBIGUOUS": (
                    "Mais de uma moldura visual operável correspondeu a uma janela hospedada.",
                    "WINDOW_SET_VISUAL_FRAME_AMBIGUOUS",
                ),
                "WINDOW_SET_SAME_RESOLVED_TARGET": (
                    "Dois tokens diferentes resolveram para a mesma moldura visual.",
                    "WINDOW_SET_SAME_RESOLVED_TARGET",
                ),
                "WINDOW_SET_NORMAL_STATE_REQUIRED": (
                    "Todas as janelas precisam estar em estado normal antes do arranjo.",
                    "WINDOW_SET_NORMAL_STATE_REQUIRED",
                ),
                "WINDOW_SET_ORIGINAL_RECT_FAILED": (
                    "Não foi possível guardar todos os retângulos originais.",
                    "WINDOW_SET_ORIGINAL_RECT_FAILED",
                ),
                "WINDOW_SET_MONITOR_NOT_FOUND": (
                    "Não foi possível identificar o monitor de todas as janelas.",
                    "WINDOW_SET_MONITOR_NOT_FOUND",
                ),
                "WINDOW_SET_MONITOR_MISMATCH": (
                    "Todas as janelas precisam estar no mesmo monitor.",
                    "WINDOW_SET_MONITOR_MISMATCH",
                ),
                "WINDOW_SET_MONITOR_INFO_FAILED": (
                    "Não foi possível obter a área útil do monitor compartilhado.",
                    "WINDOW_SET_MONITOR_INFO_FAILED",
                ),
                "WINDOW_SET_WORK_AREA_INVALID": (
                    "A área útil do monitor compartilhado é inválida.",
                    "WINDOW_SET_WORK_AREA_INVALID",
                ),
                "WINDOW_SET_MOVE_NOT_ACCEPTED": (
                    "O Windows não aceitou uma das movimentações do conjunto.",
                    "WINDOW_SET_MOVE_NOT_ACCEPTED",
                ),
                "WINDOW_SET_NOT_VERIFIED": (
                    "O Windows não confirmou um dos retângulos finais exatos.",
                    "WINDOW_SET_NOT_VERIFIED",
                ),
                "WINDOW_SET_ROLLBACK_FAILED": (
                    "O arranjo falhou e o rollback exato do conjunto não foi verificado.",
                    "WINDOW_SET_ROLLBACK_FAILED",
                ),
            }
            mapped = error_map.get(base_reason)
            if mapped is not None:
                message, error_code = mapped
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=message,
                    evidence={"reason": reason},
                    error_code=error_code,
                )
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar o arranjo multi-janela.",
                evidence={"reason": reason},
                error_code="WINDOW_SET_PLACEMENT_FAILED",
            )
        except OSError as exc:
            return ActionResult(
                request_id=request.request_id,
                success=False,
                message="Não consegui aplicar o arranjo multi-janela.",
                evidence={"exception": type(exc).__name__},
                error_code="WINDOW_SET_PLACEMENT_FAILED",
            )

        targets = evidence["targets"]
        summary = " + ".join(
            f"{target['title']} (PID {target['pid']})"
            for target in targets
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"{len(targets)} janelas organizadas em {arrangement} "
                f"({layout_spec.label_pt}) e todos os retângulos verificados: "
                f"{summary}."
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
        observation_handle = request.arguments.get("observation_handle")
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

        validated_observation = None
        if observation_handle is not None:
            try:
                validated_observation = validate_window_observation_handle(
                    observation_handle,
                    expected_target_token=target_token,
                )
            except WindowObservationHandleError as exc:
                messages = {
                    "WINDOW_OBSERVATION_EXPIRED": (
                        "A referência de observação da janela expirou; "
                        "inspecione as janelas novamente."
                    ),
                    "WINDOW_OBSERVATION_TARGET_MISMATCH": (
                        "A referência de observação não corresponde ao alvo opaco."
                    ),
                    "WINDOW_OBSERVATION_HANDLE_INVALID": (
                        "A referência de observação da janela é inválida."
                    ),
                }
                return ActionResult(
                    request_id=request.request_id,
                    success=False,
                    message=messages.get(
                        exc.code,
                        "A referência de observação da janela é inválida.",
                    ),
                    error_code=exc.code,
                    effect_dispatched=False,
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

        evidence["observation_handle_validated"] = (
            validated_observation is not None
        )
        if validated_observation is not None:
            evidence["observation_id"] = validated_observation["observation_id"]
            evidence["observation_handle_version"] = validated_observation["version"]

        observation_note = (
            " Referência de observação temporária validada."
            if validated_observation is not None
            else ""
        )
        return ActionResult(
            request_id=request.request_id,
            success=True,
            message=(
                f"Janela exata maximizada e verificada: {evidence['title']} "
                f"(PID {evidence['pid']}).{observation_note}"
            ),
            evidence=evidence,
            effect_dispatched=not bool(evidence["already_maximized"]),
            postcondition_verified=bool(evidence["maximized_verified"]),
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
