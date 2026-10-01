from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk


@dataclass(frozen=True, slots=True)
class MouseScrollSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    intent_pt: str
    preview_effect: str


_MOUSE_SCROLL_SPECS: tuple[MouseScrollSpec, ...] = (
    MouseScrollSpec(
        name="UP",
        label_pt="para cima",
        risk=ActionRisk.CONFIRM,
        intent_pt="rolar uma unidade para cima",
        preview_effect=(
            "A rolagem para cima pode mover o conteúdo visível, seleção ou outro estado "
            "definido pelo controle sob o cursor. O THE OS não inspeciona semanticamente "
            "o resultado."
        ),
    ),
    MouseScrollSpec(
        name="DOWN",
        label_pt="para baixo",
        risk=ActionRisk.CONFIRM,
        intent_pt="rolar uma unidade para baixo",
        preview_effect=(
            "A rolagem para baixo pode mover o conteúdo visível, seleção ou outro estado "
            "definido pelo controle sob o cursor. O THE OS não inspeciona semanticamente "
            "o resultado."
        ),
    ),
)


def _build_registry() -> Mapping[str, MouseScrollSpec]:
    registry = {spec.name: spec for spec in _MOUSE_SCROLL_SPECS}
    if len(registry) != len(_MOUSE_SCROLL_SPECS):
        raise RuntimeError("DUPLICATE_MOUSE_SCROLL_SPEC")
    for spec in _MOUSE_SCROLL_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_MOUSE_SCROLL_NAME:{spec.name}")
    return MappingProxyType(registry)


MOUSE_SCROLL_REGISTRY = _build_registry()
MOUSE_SCROLL_SPECS: tuple[MouseScrollSpec, ...] = tuple(
    MOUSE_SCROLL_REGISTRY.values()
)
ALLOWED_MOUSE_SCROLL_DIRECTIONS: tuple[str, ...] = tuple(
    MOUSE_SCROLL_REGISTRY
)


def get_mouse_scroll_spec(value: object) -> MouseScrollSpec | None:
    if not isinstance(value, str):
        return None
    return MOUSE_SCROLL_REGISTRY.get(value)


def is_allowed_mouse_scroll_direction(value: object) -> bool:
    return get_mouse_scroll_spec(value) is not None


def format_mouse_scroll_allowlist_pt() -> str:
    names = [spec.name for spec in MOUSE_SCROLL_SPECS]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def build_mouse_scroll_tool_description() -> str:
    operations = ", ".join(
        f"{spec.intent_pt} ({spec.name})"
        for spec in MOUSE_SCROLL_SPECS
    )
    return (
        "Rola uma unidade fixa da roda do mouse no centro de uma janela visível exata "
        "já conhecida por PID, título e target_token retornados pelo mesmo "
        f"window_snapshot. Operações registradas: {operations}. A posição continua "
        "fixa no centro da janela e cada chamada envia exatamente um evento de wheel "
        "com magnitude local fixa. Coordenadas arbitrárias, quantidade arbitrária, "
        "scroll horizontal, drag e double-click permanecem bloqueados. O THE OS "
        "verifica alvo, posição do cursor, envio e foco, mas não inspeciona o efeito "
        "semântico da rolagem."
    )
