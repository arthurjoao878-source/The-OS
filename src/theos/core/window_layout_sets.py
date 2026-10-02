from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk
from theos.core.window_layout_pairs import (
    HOSTED_FRAME_WINDOW_CLASS,
    HostedWindowCandidate,
    resolve_hosted_visual_frame,
)
from theos.core.window_placements import get_window_placement_spec


@dataclass(frozen=True, slots=True)
class WindowSetLayoutSpec:
    name: str
    label_pt: str
    risk: ActionRisk
    target_count: int
    placements: tuple[str, ...]
    intent_pt: str


_WINDOW_SET_LAYOUT_SPECS: tuple[WindowSetLayoutSpec, ...] = (
    WindowSetLayoutSpec(
        name="THREE_COLUMNS",
        label_pt="três colunas",
        risk=ActionRisk.NORMAL,
        target_count=3,
        placements=("LEFT_THIRD", "CENTER_THIRD", "RIGHT_THIRD"),
        intent_pt=(
            "organizar três janelas em colunas esquerda, central e direita "
            "no mesmo monitor"
        ),
    ),
    WindowSetLayoutSpec(
        name="LEFT_MAIN_RIGHT_STACK",
        label_pt="principal à esquerda e duas à direita",
        risk=ActionRisk.NORMAL,
        target_count=3,
        placements=(
            "LEFT_HALF",
            "UPPER_RIGHT_QUADRANT",
            "LOWER_RIGHT_QUADRANT",
        ),
        intent_pt=(
            "organizar a primeira janela na metade esquerda e empilhar "
            "a segunda e a terceira na metade direita"
        ),
    ),
    WindowSetLayoutSpec(
        name="RIGHT_MAIN_LEFT_STACK",
        label_pt="principal à direita e duas à esquerda",
        risk=ActionRisk.NORMAL,
        target_count=3,
        placements=(
            "RIGHT_HALF",
            "UPPER_LEFT_QUADRANT",
            "LOWER_LEFT_QUADRANT",
        ),
        intent_pt=(
            "organizar a primeira janela na metade direita e empilhar "
            "a segunda e a terceira na metade esquerda"
        ),
    ),
    WindowSetLayoutSpec(
        name="FOUR_QUADRANTS",
        label_pt="quatro quadrantes",
        risk=ActionRisk.NORMAL,
        target_count=4,
        placements=(
            "UPPER_LEFT_QUADRANT",
            "UPPER_RIGHT_QUADRANT",
            "LOWER_LEFT_QUADRANT",
            "LOWER_RIGHT_QUADRANT",
        ),
        intent_pt=(
            "organizar quatro janelas nos quatro quadrantes do mesmo monitor"
        ),
    ),
)


def _placement_rect_percent(name: str) -> tuple[int, int, int, int]:
    placement = get_window_placement_spec(name)
    if placement is None:
        raise RuntimeError(f"INVALID_WINDOW_SET_LAYOUT_PLACEMENT:{name}")
    return (
        placement.x_percent,
        placement.y_percent,
        placement.x_percent + placement.width_percent,
        placement.y_percent + placement.height_percent,
    )


def _rectangles_overlap(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> bool:
    return (
        max(first[0], second[0]) < min(first[2], second[2])
        and max(first[1], second[1]) < min(first[3], second[3])
    )


def _build_registry() -> Mapping[str, WindowSetLayoutSpec]:
    registry = {spec.name: spec for spec in _WINDOW_SET_LAYOUT_SPECS}
    if len(registry) != len(_WINDOW_SET_LAYOUT_SPECS):
        raise RuntimeError("DUPLICATE_WINDOW_SET_LAYOUT_SPEC")

    for spec in _WINDOW_SET_LAYOUT_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_WINDOW_SET_LAYOUT_NAME:{spec.name}")
        if spec.risk is not ActionRisk.NORMAL:
            raise RuntimeError(f"INVALID_WINDOW_SET_LAYOUT_RISK:{spec.name}")
        if spec.target_count not in (3, 4):
            raise RuntimeError(f"INVALID_WINDOW_SET_TARGET_COUNT:{spec.name}")
        if len(spec.placements) != spec.target_count:
            raise RuntimeError(f"WINDOW_SET_PLACEMENT_COUNT_MISMATCH:{spec.name}")
        if len(set(spec.placements)) != len(spec.placements):
            raise RuntimeError(f"DUPLICATE_WINDOW_SET_PLACEMENT:{spec.name}")

        rectangles = tuple(
            _placement_rect_percent(placement)
            for placement in spec.placements
        )
        for index, first in enumerate(rectangles):
            for second in rectangles[index + 1 :]:
                if _rectangles_overlap(first, second):
                    raise RuntimeError(f"OVERLAPPING_WINDOW_SET_LAYOUT:{spec.name}")

        covered_percent_area = sum(
            (right - left) * (bottom - top)
            for left, top, right, bottom in rectangles
        )
        if covered_percent_area != 10_000:
            raise RuntimeError(f"INCOMPLETE_WINDOW_SET_LAYOUT:{spec.name}")

    return MappingProxyType(registry)


WINDOW_SET_LAYOUT_REGISTRY = _build_registry()
WINDOW_SET_LAYOUT_SPECS: tuple[WindowSetLayoutSpec, ...] = tuple(
    WINDOW_SET_LAYOUT_REGISTRY.values()
)
ALLOWED_WINDOW_SET_LAYOUTS: tuple[str, ...] = tuple(WINDOW_SET_LAYOUT_REGISTRY)


def get_window_set_layout_spec(value: object) -> WindowSetLayoutSpec | None:
    if not isinstance(value, str):
        return None
    return WINDOW_SET_LAYOUT_REGISTRY.get(value)


def is_allowed_window_set_layout(value: object) -> bool:
    return get_window_set_layout_spec(value) is not None


def resolve_hosted_visual_frame_for_set(
    selected: HostedWindowCandidate,
    candidates: tuple[HostedWindowCandidate, ...],
    dwm_cloaked_by_hwnd: Mapping[int, int | None],
) -> tuple[HostedWindowCandidate, bool, bool]:
    """Resolve hosted frame, using unique uncloaked frame only as ambiguity tie-break."""
    try:
        resolved, normalized = resolve_hosted_visual_frame(
            selected,
            candidates,
        )
        return resolved, normalized, False
    except ValueError as exc:
        if str(exc) != "HOSTED_VISUAL_FRAME_AMBIGUOUS":
            raise

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
    unique_uncloaked = tuple(
        candidate
        for candidate in eligible_frames
        if dwm_cloaked_by_hwnd.get(candidate.hwnd) == 0
    )
    if len(unique_uncloaked) != 1:
        raise ValueError("HOSTED_VISUAL_FRAME_AMBIGUOUS")

    return unique_uncloaked[0], True, True


def build_window_set_layout_tool_description() -> str:
    layouts = ", ".join(
        f"{spec.label_pt} ({spec.name}, {spec.target_count} janelas)"
        for spec in WINDOW_SET_LAYOUT_SPECS
    )
    return (
        "Organiza três ou quatro janelas visíveis exatas em um arranjo registrado "
        "no mesmo monitor, com rollback local de todo o conjunto se uma movimentação "
        f"parcial falhar. Arranjos permitidos: {layouts}. A ordem dos target_tokens "
        "define qual janela ocupa cada posição do arranjo. Todas as janelas precisam "
        "estar em estado normal antes da primeira mutação. Os alvos devem vir de "
        "window_snapshot_many; o modelo fornece somente target_tokens opacos e o "
        "nome do arranjo, sem PID/título duplicados, coordenadas, pixels, tamanhos, "
        "percentuais ou seleção de monitor."
    )
