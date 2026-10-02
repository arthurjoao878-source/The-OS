from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk
from theos.core.window_targets import build_hosted_window_target_guidance


@dataclass(frozen=True, slots=True)
class WindowKeySpec:
    name: str
    risk: ActionRisk
    intent_pt: str
    preview_effect: str


_DIRECTIONAL_PREVIEW = (
    "UP/DOWN/LEFT/RIGHT podem navegar direcionalmente no controle em foco. "
    "O THE OS não inspeciona semanticamente o destino da navegação."
)
_BOUNDARY_PREVIEW = (
    "HOME/END/PAGE_UP/PAGE_DOWN podem navegar por limites ou páginas no controle em foco. "
    "O THE OS não inspeciona semanticamente a posição resultante."
)
_DESTRUCTIVE_EDIT_PREVIEW = (
    "ATENÇÃO: BACKSPACE e DELETE podem remover texto, itens ou outros dados dependendo "
    "do controle que estiver em foco. O efeito interno do aplicativo não será inspecionado."
)


_WINDOW_KEY_SPECS: tuple[WindowKeySpec, ...] = (
    WindowKeySpec(
        name="ENTER",
        risk=ActionRisk.CONFIRM,
        intent_pt="confirmar ou enviar com Enter",
        preview_effect=(
            "ENTER pode confirmar/enviar a ação do controle em foco. "
            "O THE OS não inspeciona semanticamente o resultado."
        ),
    ),
    WindowKeySpec(
        name="ESCAPE",
        risk=ActionRisk.CONFIRM,
        intent_pt="cancelar ou fechar estado transitório com Escape",
        preview_effect=(
            "ESCAPE pode cancelar ou fechar um estado transitório do aplicativo. "
            "O THE OS não inspeciona semanticamente o resultado."
        ),
    ),
    WindowKeySpec(
        name="TAB",
        risk=ActionRisk.CONFIRM,
        intent_pt="mover foco com Tab",
        preview_effect=(
            "TAB pode mover o foco entre controles. "
            "O THE OS não inspeciona qual controle receberá o foco."
        ),
    ),
    WindowKeySpec(name="UP", risk=ActionRisk.CONFIRM, intent_pt="navegar para cima", preview_effect=_DIRECTIONAL_PREVIEW),
    WindowKeySpec(name="DOWN", risk=ActionRisk.CONFIRM, intent_pt="navegar para baixo", preview_effect=_DIRECTIONAL_PREVIEW),
    WindowKeySpec(name="LEFT", risk=ActionRisk.CONFIRM, intent_pt="navegar para a esquerda", preview_effect=_DIRECTIONAL_PREVIEW),
    WindowKeySpec(name="RIGHT", risk=ActionRisk.CONFIRM, intent_pt="navegar para a direita", preview_effect=_DIRECTIONAL_PREVIEW),
    WindowKeySpec(name="HOME", risk=ActionRisk.CONFIRM, intent_pt="navegar para o início", preview_effect=_BOUNDARY_PREVIEW),
    WindowKeySpec(name="END", risk=ActionRisk.CONFIRM, intent_pt="navegar para o fim", preview_effect=_BOUNDARY_PREVIEW),
    WindowKeySpec(name="PAGE_UP", risk=ActionRisk.CONFIRM, intent_pt="navegar uma página para cima", preview_effect=_BOUNDARY_PREVIEW),
    WindowKeySpec(name="PAGE_DOWN", risk=ActionRisk.CONFIRM, intent_pt="navegar uma página para baixo", preview_effect=_BOUNDARY_PREVIEW),
    WindowKeySpec(name="BACKSPACE", risk=ActionRisk.DESTRUCTIVE, intent_pt="apagar com Backspace", preview_effect=_DESTRUCTIVE_EDIT_PREVIEW),
    WindowKeySpec(name="DELETE", risk=ActionRisk.DESTRUCTIVE, intent_pt="apagar com Delete", preview_effect=_DESTRUCTIVE_EDIT_PREVIEW),
)


def _build_registry() -> Mapping[str, WindowKeySpec]:
    registry = {spec.name: spec for spec in _WINDOW_KEY_SPECS}
    if len(registry) != len(_WINDOW_KEY_SPECS):
        raise RuntimeError("DUPLICATE_WINDOW_KEY_SPEC")
    for spec in _WINDOW_KEY_SPECS:
        if not spec.name or spec.name != spec.name.upper():
            raise RuntimeError(f"INVALID_WINDOW_KEY_NAME:{spec.name}")
    return MappingProxyType(registry)


WINDOW_KEY_REGISTRY = _build_registry()
WINDOW_KEY_SPECS: tuple[WindowKeySpec, ...] = tuple(WINDOW_KEY_REGISTRY.values())
ALLOWED_WINDOW_KEYS: tuple[str, ...] = tuple(WINDOW_KEY_REGISTRY)
DESTRUCTIVE_WINDOW_KEYS: frozenset[str] = frozenset(
    spec.name for spec in WINDOW_KEY_SPECS if spec.risk is ActionRisk.DESTRUCTIVE
)


def get_window_key_spec(value: object) -> WindowKeySpec | None:
    if not isinstance(value, str):
        return None
    return WINDOW_KEY_REGISTRY.get(value)


def is_allowed_window_key(value: object) -> bool:
    return get_window_key_spec(value) is not None


def is_destructive_window_key(value: object) -> bool:
    spec = get_window_key_spec(value)
    return spec is not None and spec.risk is ActionRisk.DESTRUCTIVE


def format_window_key_allowlist_pt() -> str:
    names = [spec.name for spec in WINDOW_KEY_SPECS]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def build_window_key_tool_description() -> str:
    operations = ", ".join(f"{spec.intent_pt} ({spec.name})" for spec in WINDOW_KEY_SPECS)
    confirm = ", ".join(spec.name for spec in WINDOW_KEY_SPECS if spec.risk is ActionRisk.CONFIRM)
    destructive = ", ".join(spec.name for spec in WINDOW_KEY_SPECS if spec.risk is ActionRisk.DESTRUCTIVE)
    return (
        "Pressiona uma tecla permitida em uma janela visível exata já conhecida por PID, "
        "título e target_token retornados pelo mesmo window_snapshot. Use somente quando "
        f"o usuário pedir explicitamente uma das operações registradas: {operations}. "
        f"Classificação local atual: CONFIRM = {confirm}; DESTRUCTIVE = {destructive}. "
        "Teclas não registradas, modificadores e combinações arbitrárias permanecem "
        "bloqueados. O efeito interno do aplicativo não é lido nem inferido."
    ) + build_hosted_window_target_guidance()
