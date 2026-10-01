from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk


@dataclass(frozen=True, slots=True)
class WindowPlacementSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    x_percent: int
    y_percent: int
    width_percent: int
    height_percent: int
    intent_pt: str


_WINDOW_PLACEMENT_SPECS: tuple[WindowPlacementSpec, ...] = (
    WindowPlacementSpec(
        name="LEFT_HALF",
        label_pt="metade esquerda",
        risk=ActionRisk.NORMAL,
        x_percent=0,
        y_percent=0,
        width_percent=50,
        height_percent=100,
        intent_pt="ocupar a metade esquerda da área útil do monitor atual",
    ),
    WindowPlacementSpec(
        name="RIGHT_HALF",
        label_pt="metade direita",
        risk=ActionRisk.NORMAL,
        x_percent=50,
        y_percent=0,
        width_percent=50,
        height_percent=100,
        intent_pt="ocupar a metade direita da área útil do monitor atual",
    ),
    WindowPlacementSpec(
        name="UPPER_LEFT_QUADRANT",
        label_pt="quadrante superior esquerdo",
        risk=ActionRisk.NORMAL,
        x_percent=0,
        y_percent=0,
        width_percent=50,
        height_percent=50,
        intent_pt="ocupar o quadrante superior esquerdo da área útil do monitor atual",
    ),
    WindowPlacementSpec(
        name="UPPER_RIGHT_QUADRANT",
        label_pt="quadrante superior direito",
        risk=ActionRisk.NORMAL,
        x_percent=50,
        y_percent=0,
        width_percent=50,
        height_percent=50,
        intent_pt="ocupar o quadrante superior direito da área útil do monitor atual",
    ),
    WindowPlacementSpec(
        name="LOWER_LEFT_QUADRANT",
        label_pt="quadrante inferior esquerdo",
        risk=ActionRisk.NORMAL,
        x_percent=0,
        y_percent=50,
        width_percent=50,
        height_percent=50,
        intent_pt="ocupar o quadrante inferior esquerdo da área útil do monitor atual",
    ),
    WindowPlacementSpec(
        name="LOWER_RIGHT_QUADRANT",
        label_pt="quadrante inferior direito",
        risk=ActionRisk.NORMAL,
        x_percent=50,
        y_percent=50,
        width_percent=50,
        height_percent=50,
        intent_pt="ocupar o quadrante inferior direito da área útil do monitor atual",
    ),
)


def _build_registry() -> Mapping[str, WindowPlacementSpec]:
    registry = {spec.name: spec for spec in _WINDOW_PLACEMENT_SPECS}
    if len(registry) != len(_WINDOW_PLACEMENT_SPECS):
        raise RuntimeError("DUPLICATE_WINDOW_PLACEMENT_SPEC")

    for spec in _WINDOW_PLACEMENT_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_NAME:{spec.name}")
        if spec.risk is not ActionRisk.NORMAL:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_RISK:{spec.name}")
        if spec.x_percent not in {0, 50} or spec.y_percent not in {0, 50}:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_ORIGIN:{spec.name}")
        if spec.width_percent not in {50}:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_WIDTH:{spec.name}")
        if spec.height_percent not in {50, 100}:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_HEIGHT:{spec.name}")
        if spec.x_percent + spec.width_percent > 100:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_HORIZONTAL_BOUNDS:{spec.name}")
        if spec.y_percent + spec.height_percent > 100:
            raise RuntimeError(f"INVALID_WINDOW_PLACEMENT_VERTICAL_BOUNDS:{spec.name}")

    return MappingProxyType(registry)


WINDOW_PLACEMENT_REGISTRY = _build_registry()
WINDOW_PLACEMENT_SPECS: tuple[WindowPlacementSpec, ...] = tuple(
    WINDOW_PLACEMENT_REGISTRY.values()
)
ALLOWED_WINDOW_PLACEMENTS: tuple[str, ...] = tuple(WINDOW_PLACEMENT_REGISTRY)


def get_window_placement_spec(value: object) -> WindowPlacementSpec | None:
    if not isinstance(value, str):
        return None
    return WINDOW_PLACEMENT_REGISTRY.get(value)


def is_allowed_window_placement(value: object) -> bool:
    return get_window_placement_spec(value) is not None


def build_window_placement_tool_description() -> str:
    layouts = ", ".join(
        f"{spec.label_pt} ({spec.name})"
        for spec in WINDOW_PLACEMENT_SPECS
    )
    return (
        "Reposiciona e redimensiona uma janela visível exata para um layout registrado "
        "na área útil do monitor em que ela está. Layouts permitidos: "
        f"{layouts}. A geometria é calculada localmente a partir do rcWork do monitor "
        "atual; o modelo não fornece x, y, largura, altura, monitor ou pixels. Janelas "
        "minimizadas ou maximizadas são restauradas ao estado normal antes da aplicação "
        "do layout. O THE OS verifica o retângulo final exato com GetWindowRect e não "
        "afirma semântica nativa de Snap do Windows."
    )
