from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk


@dataclass(frozen=True, slots=True)
class MouseButtonSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    intent_pt: str
    preview_effect: str


_MOUSE_BUTTON_SPECS: tuple[MouseButtonSpec, ...] = (
    MouseButtonSpec(
        name="LEFT",
        label_pt="esquerdo",
        risk=ActionRisk.CONFIRM,
        intent_pt="clicar com o botão esquerdo",
        preview_effect=(
            "O clique esquerdo pode ativar, selecionar ou executar o controle localizado "
            "no centro da janela. O THE OS não inspeciona semanticamente o efeito."
        ),
    ),
    MouseButtonSpec(
        name="RIGHT",
        label_pt="direito",
        risk=ActionRisk.CONFIRM,
        intent_pt="clicar com o botão direito",
        preview_effect=(
            "O clique direito pode abrir um menu de contexto ou executar outra ação "
            "definida pelo controle no centro da janela. O THE OS não inspeciona "
            "semanticamente o efeito."
        ),
    ),
    MouseButtonSpec(
        name="MIDDLE",
        label_pt="do meio",
        risk=ActionRisk.CONFIRM,
        intent_pt="clicar com o botão do meio",
        preview_effect=(
            "O clique do meio pode acionar navegação, rolagem automática ou outra ação "
            "definida pelo controle no centro da janela. O THE OS não inspeciona "
            "semanticamente o efeito."
        ),
    ),
)


def _build_registry() -> Mapping[str, MouseButtonSpec]:
    registry = {spec.name: spec for spec in _MOUSE_BUTTON_SPECS}
    if len(registry) != len(_MOUSE_BUTTON_SPECS):
        raise RuntimeError("DUPLICATE_MOUSE_BUTTON_SPEC")
    for spec in _MOUSE_BUTTON_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_MOUSE_BUTTON_NAME:{spec.name}")
    return MappingProxyType(registry)


MOUSE_BUTTON_REGISTRY = _build_registry()
MOUSE_BUTTON_SPECS: tuple[MouseButtonSpec, ...] = tuple(
    MOUSE_BUTTON_REGISTRY.values()
)
ALLOWED_MOUSE_BUTTONS: tuple[str, ...] = tuple(MOUSE_BUTTON_REGISTRY)


def get_mouse_button_spec(value: object) -> MouseButtonSpec | None:
    if not isinstance(value, str):
        return None
    return MOUSE_BUTTON_REGISTRY.get(value)


def is_allowed_mouse_button(value: object) -> bool:
    return get_mouse_button_spec(value) is not None


def format_mouse_button_allowlist_pt() -> str:
    names = [spec.name for spec in MOUSE_BUTTON_SPECS]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def build_mouse_click_tool_description() -> str:
    operations = ", ".join(
        f"{spec.intent_pt} ({spec.name})"
        for spec in MOUSE_BUTTON_SPECS
    )
    return (
        "Clica exatamente no centro de uma janela visível já conhecida por PID, título "
        "e target_token retornados pelo mesmo window_snapshot. Use somente quando o "
        f"usuário pedir explicitamente uma operação registrada: {operations}. "
        "A posição é fixa no centro da janela; coordenadas arbitrárias, arrastar, "
        "double-click e wheel permanecem bloqueados. O THE OS verifica alvo, posição "
        "do cursor, envio dos dois eventos e foco, mas não lê o conteúdo da janela nem "
        "afirma o efeito semântico do clique."
    )
