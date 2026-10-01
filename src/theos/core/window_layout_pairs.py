from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk
from theos.core.window_placements import get_window_placement_spec


@dataclass(frozen=True, slots=True)
class WindowPairLayoutSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    first_placement: str
    second_placement: str
    intent_pt: str


_WINDOW_PAIR_LAYOUT_SPECS: tuple[WindowPairLayoutSpec, ...] = (
    WindowPairLayoutSpec(
        name="SIDE_BY_SIDE",
        label_pt="lado a lado",
        risk=ActionRisk.NORMAL,
        first_placement="LEFT_HALF",
        second_placement="RIGHT_HALF",
        intent_pt=(
            "organizar a primeira janela na metade esquerda e a segunda "
            "na metade direita do mesmo monitor"
        ),
    ),
    WindowPairLayoutSpec(
        name="STACKED",
        label_pt="empilhadas",
        risk=ActionRisk.NORMAL,
        first_placement="TOP_HALF",
        second_placement="BOTTOM_HALF",
        intent_pt=(
            "organizar a primeira janela na metade superior e a segunda "
            "na metade inferior do mesmo monitor"
        ),
    ),
)


def _build_registry() -> Mapping[str, WindowPairLayoutSpec]:
    registry = {spec.name: spec for spec in _WINDOW_PAIR_LAYOUT_SPECS}
    if len(registry) != len(_WINDOW_PAIR_LAYOUT_SPECS):
        raise RuntimeError("DUPLICATE_WINDOW_PAIR_LAYOUT_SPEC")

    for spec in _WINDOW_PAIR_LAYOUT_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_WINDOW_PAIR_LAYOUT_NAME:{spec.name}")
        if spec.risk is not ActionRisk.NORMAL:
            raise RuntimeError(f"INVALID_WINDOW_PAIR_LAYOUT_RISK:{spec.name}")
        first = get_window_placement_spec(spec.first_placement)
        second = get_window_placement_spec(spec.second_placement)
        if first is None or second is None:
            raise RuntimeError(f"INVALID_WINDOW_PAIR_LAYOUT_PLACEMENT:{spec.name}")
        if spec.first_placement == spec.second_placement:
            raise RuntimeError(f"OVERLAPPING_WINDOW_PAIR_LAYOUT:{spec.name}")

    return MappingProxyType(registry)


WINDOW_PAIR_LAYOUT_REGISTRY = _build_registry()
WINDOW_PAIR_LAYOUT_SPECS: tuple[WindowPairLayoutSpec, ...] = tuple(
    WINDOW_PAIR_LAYOUT_REGISTRY.values()
)
ALLOWED_WINDOW_PAIR_LAYOUTS: tuple[str, ...] = tuple(WINDOW_PAIR_LAYOUT_REGISTRY)


def get_window_pair_layout_spec(value: object) -> WindowPairLayoutSpec | None:
    if not isinstance(value, str):
        return None
    return WINDOW_PAIR_LAYOUT_REGISTRY.get(value)


def is_allowed_window_pair_layout(value: object) -> bool:
    return get_window_pair_layout_spec(value) is not None


def build_window_pair_layout_tool_description() -> str:
    layouts = ", ".join(
        f"{spec.label_pt} ({spec.name})"
        for spec in WINDOW_PAIR_LAYOUT_SPECS
    )
    return (
        "Organiza duas janelas visíveis exatas em um arranjo registrado no mesmo "
        "monitor, com rollback local se uma movimentação parcial falhar. Arranjos "
        f"permitidos: {layouts}. As duas janelas devem estar em estado normal; "
        "minimizadas ou maximizadas são bloqueadas antes de qualquer movimento. "
        "Cada alvo deve vir de window_snapshot ou window_snapshot_many e possuir "
        "PID, título e target_token exatos. O modelo não fornece coordenadas, "
        "tamanhos, percentuais, pixels ou monitor. O THE OS verifica os dois "
        "retângulos finais com GetWindowRect e não afirma semântica nativa de Snap."
    )

HOSTED_CONTENT_WINDOW_CLASS = "Windows.UI.Core.CoreWindow"
HOSTED_FRAME_WINDOW_CLASS = "ApplicationFrameWindow"


@dataclass(frozen=True, slots=True)
class HostedWindowCandidate:
    hwnd: int
    pid: int
    title: str
    target_token: str
    class_name: str
    is_iconic: bool
    is_zoomed: bool
    client_width: int
    client_height: int


def resolve_hosted_visual_frame(
    selected: HostedWindowCandidate,
    candidates: tuple[HostedWindowCandidate, ...],
) -> tuple[HostedWindowCandidate, bool]:
    hosted_classes = {
        HOSTED_CONTENT_WINDOW_CLASS,
        HOSTED_FRAME_WINDOW_CLASS,
    }
    if selected.class_name not in hosted_classes:
        return selected, False

    selected_is_eligible_frame = (
        selected.class_name == HOSTED_FRAME_WINDOW_CLASS
        and not selected.is_iconic
        and not selected.is_zoomed
        and selected.client_width > 0
        and selected.client_height > 0
    )
    if selected_is_eligible_frame:
        return selected, False

    eligible_frames = tuple(
        candidate
        for candidate in candidates
        if candidate.title == selected.title
        and candidate.class_name == HOSTED_FRAME_WINDOW_CLASS
        and not candidate.is_iconic
        and not candidate.is_zoomed
        and candidate.client_width > 0
        and candidate.client_height > 0
    )
    if not eligible_frames:
        raise ValueError("HOSTED_VISUAL_FRAME_NOT_FOUND")
    if len(eligible_frames) != 1:
        raise ValueError("HOSTED_VISUAL_FRAME_AMBIGUOUS")

    return eligible_frames[0], True
