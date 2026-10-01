from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class MouseAnchorSpec:
    name: str
    label_pt: str
    x_percent: int
    y_percent: int


_MOUSE_ANCHOR_SPECS: tuple[MouseAnchorSpec, ...] = (
    MouseAnchorSpec(
        name="UPPER_LEFT",
        label_pt="superior esquerda",
        x_percent=25,
        y_percent=25,
    ),
    MouseAnchorSpec(
        name="UPPER_RIGHT",
        label_pt="superior direita",
        x_percent=75,
        y_percent=25,
    ),
    MouseAnchorSpec(
        name="LOWER_LEFT",
        label_pt="inferior esquerda",
        x_percent=25,
        y_percent=75,
    ),
    MouseAnchorSpec(
        name="LOWER_RIGHT",
        label_pt="inferior direita",
        x_percent=75,
        y_percent=75,
    ),
)


def _build_registry() -> Mapping[str, MouseAnchorSpec]:
    registry = {spec.name: spec for spec in _MOUSE_ANCHOR_SPECS}
    if len(registry) != len(_MOUSE_ANCHOR_SPECS):
        raise RuntimeError("DUPLICATE_MOUSE_ANCHOR_SPEC")
    for spec in _MOUSE_ANCHOR_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_MOUSE_ANCHOR_NAME:{spec.name}")
        if not 0 < spec.x_percent < 100 or not 0 < spec.y_percent < 100:
            raise RuntimeError(f"INVALID_MOUSE_ANCHOR_PERCENT:{spec.name}")
    return MappingProxyType(registry)


MOUSE_ANCHOR_REGISTRY = _build_registry()
MOUSE_ANCHOR_SPECS: tuple[MouseAnchorSpec, ...] = tuple(
    MOUSE_ANCHOR_REGISTRY.values()
)
ALLOWED_MOUSE_ANCHORS: tuple[str, ...] = tuple(MOUSE_ANCHOR_REGISTRY)


def get_mouse_anchor_spec(value: object) -> MouseAnchorSpec | None:
    if not isinstance(value, str):
        return None
    return MOUSE_ANCHOR_REGISTRY.get(value)


def is_allowed_mouse_anchor(value: object) -> bool:
    return get_mouse_anchor_spec(value) is not None


def format_mouse_anchor_allowlist_pt() -> str:
    names = [spec.name for spec in MOUSE_ANCHOR_SPECS]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def build_mouse_anchor_click_tool_description() -> str:
    anchors = ", ".join(
        f"{spec.label_pt} ({spec.name}, {spec.x_percent}%/{spec.y_percent}%)"
        for spec in MOUSE_ANCHOR_SPECS
    )
    return (
        "Clica em uma âncora interna registrada da área cliente de uma janela visível "
        "exata já conhecida por PID, título e target_token retornados pelo mesmo "
        f"window_snapshot. Âncoras permitidas: {anchors}. A posição é derivada "
        "localmente da área cliente usando apenas percentuais fixos; não aceita x/y, "
        "pixels arbitrários, bordas da janela ou barra de título. Use click_window "
        "quando o pedido for especificamente o centro geométrico da janela inteira. "
        "O THE OS verifica alvo, posição do cursor, envio dos dois eventos e foco, "
        "mas não lê controles nem afirma o efeito semântico do clique."
    )
