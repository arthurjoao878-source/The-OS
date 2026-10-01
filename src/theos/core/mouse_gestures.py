from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk


@dataclass(frozen=True, slots=True)
class MouseGestureSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    intent_pt: str
    event_count: int
    preview_effect: str


_MOUSE_GESTURE_SPECS: tuple[MouseGestureSpec, ...] = (
    MouseGestureSpec(
        name="DOUBLE_LEFT",
        label_pt="duplo clique esquerdo",
        risk=ActionRisk.CONFIRM,
        intent_pt="dar duplo clique com o botão esquerdo",
        event_count=4,
        preview_effect=(
            "O duplo clique esquerdo pode abrir, ativar, selecionar ou executar uma "
            "ação definida pelo controle no centro da janela. O THE OS verifica apenas "
            "a sequência de entrada, posição e foco; não afirma que o aplicativo "
            "reconheceu semanticamente um duplo clique."
        ),
    ),
)


def _build_registry() -> Mapping[str, MouseGestureSpec]:
    registry = {spec.name: spec for spec in _MOUSE_GESTURE_SPECS}
    if len(registry) != len(_MOUSE_GESTURE_SPECS):
        raise RuntimeError("DUPLICATE_MOUSE_GESTURE_SPEC")
    for spec in _MOUSE_GESTURE_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_MOUSE_GESTURE_NAME:{spec.name}")
        if spec.event_count != 4:
            raise RuntimeError(f"INVALID_MOUSE_GESTURE_EVENT_COUNT:{spec.name}")
    return MappingProxyType(registry)


MOUSE_GESTURE_REGISTRY = _build_registry()
MOUSE_GESTURE_SPECS: tuple[MouseGestureSpec, ...] = tuple(
    MOUSE_GESTURE_REGISTRY.values()
)
ALLOWED_MOUSE_GESTURES: tuple[str, ...] = tuple(MOUSE_GESTURE_REGISTRY)


def get_mouse_gesture_spec(value: object) -> MouseGestureSpec | None:
    if not isinstance(value, str):
        return None
    return MOUSE_GESTURE_REGISTRY.get(value)


def is_allowed_mouse_gesture(value: object) -> bool:
    return get_mouse_gesture_spec(value) is not None


def build_mouse_double_click_tool_description() -> str:
    operations = ", ".join(
        f"{spec.intent_pt} ({spec.name})"
        for spec in MOUSE_GESTURE_SPECS
    )
    return (
        "Executa um gesto de mouse registrado no centro geométrico de uma janela "
        "visível exata já conhecida por PID, título e target_token retornados pelo "
        f"mesmo window_snapshot. Gesto permitido nesta etapa: {operations}. "
        "DOUBLE_LEFT usa exatamente quatro eventos LEFT down/up/down/up. Não aceita "
        "botão arbitrário, quantidade de cliques, intervalo, x/y, âncoras, drag ou "
        "wheel. O THE OS verifica alvo, cursor, quantidade de eventos aceita e foco, "
        "mas não lê controles nem afirma que o aplicativo reconheceu semanticamente "
        "o duplo clique."
    )
