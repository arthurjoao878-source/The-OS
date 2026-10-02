from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk
from theos.core.window_targets import build_hosted_window_target_guidance


@dataclass(frozen=True, slots=True)
class MouseDragSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    intent_pt: str
    event_count: int
    preview_effect: str


_MOUSE_DRAG_SPECS: tuple[MouseDragSpec, ...] = (
    MouseDragSpec(
        name="LEFT_DRAG",
        label_pt="arrasto com botão esquerdo",
        risk=ActionRisk.DESTRUCTIVE,
        intent_pt="arrastar com o botão esquerdo entre duas âncoras internas",
        event_count=2,
        preview_effect=(
            "O arrasto pode selecionar, mover, reorganizar ou alterar conteúdo no "
            "aplicativo. O THE OS verifica apenas a origem, o destino, o envio de "
            "LEFTDOWN/LEFTUP e a continuidade de foco; não inspeciona semanticamente "
            "o efeito produzido."
        ),
    ),
)


def _build_registry() -> Mapping[str, MouseDragSpec]:
    registry = {spec.name: spec for spec in _MOUSE_DRAG_SPECS}
    if len(registry) != len(_MOUSE_DRAG_SPECS):
        raise RuntimeError("DUPLICATE_MOUSE_DRAG_SPEC")
    for spec in _MOUSE_DRAG_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_MOUSE_DRAG_NAME:{spec.name}")
        if spec.event_count != 2:
            raise RuntimeError(f"INVALID_MOUSE_DRAG_EVENT_COUNT:{spec.name}")
    return MappingProxyType(registry)


MOUSE_DRAG_REGISTRY = _build_registry()
MOUSE_DRAG_SPECS: tuple[MouseDragSpec, ...] = tuple(MOUSE_DRAG_REGISTRY.values())
ALLOWED_MOUSE_DRAGS: tuple[str, ...] = tuple(MOUSE_DRAG_REGISTRY)


def get_mouse_drag_spec(value: object) -> MouseDragSpec | None:
    if not isinstance(value, str):
        return None
    return MOUSE_DRAG_REGISTRY.get(value)


def is_allowed_mouse_drag(value: object) -> bool:
    return get_mouse_drag_spec(value) is not None


def build_mouse_drag_tool_description() -> str:
    operations = ", ".join(
        f"{spec.intent_pt} ({spec.name})"
        for spec in MOUSE_DRAG_SPECS
    )
    return (
        "Arrasta dentro da área cliente de uma janela visível exata já conhecida por "
        "PID, título e target_token retornados pelo mesmo window_snapshot. Operação "
        f"permitida nesta etapa: {operations}. Origem e destino devem ser âncoras "
        "registradas diferentes fornecidas pelo catálogo de geometria interna, "
        "sempre na malha fixa de 25%/50%/75% com o centro exato reservado. O transporte "
        "posiciona e "
        "verifica a origem, envia um LEFTDOWN, move e verifica o destino e envia um "
        "LEFTUP. Não aceita x/y, botão arbitrário, caminho intermediário, duração, "
        "quantidade de eventos ou origem igual ao destino. O THE OS não lê controles "
        "nem afirma o efeito semântico do arrasto."
    ) + build_hosted_window_target_guidance()
