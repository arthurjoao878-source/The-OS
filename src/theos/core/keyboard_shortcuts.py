from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from theos.core.actions.contracts import ActionRisk
from theos.core.keyboard_keys import WINDOW_KEY_REGISTRY
from theos.core.window_targets import build_hosted_window_target_guidance


@dataclass(frozen=True, slots=True)
class WindowShortcutSpec:
    name: str
    label: str
    modifier: str
    primary_key: str
    risk: ActionRisk
    intent_pt: str
    preview_effect: str
    clipboard_used: bool = False
    clipboard_effect_expected: bool = False
    clipboard_input_expected: bool = False
    content_mutation_expected: bool = False


_WINDOW_SHORTCUT_SPECS: tuple[WindowShortcutSpec, ...] = (
    WindowShortcutSpec(
        name="CTRL_A",
        label="CTRL+A",
        modifier="CTRL",
        primary_key="A",
        risk=ActionRisk.CONFIRM,
        intent_pt="selecionar tudo",
        preview_effect=(
            "CTRL+A pode selecionar conteúdo dependendo do controle em foco. "
            "Nenhum conteúdo da área de transferência é lido ou escrito por esse atalho."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_C",
        label="CTRL+C",
        modifier="CTRL",
        primary_key="C",
        risk=ActionRisk.CONFIRM,
        intent_pt="copiar",
        preview_effect=(
            "ATENÇÃO: CTRL+C pode substituir o conteúdo atual da área de transferência "
            "pelo conteúdo selecionado no aplicativo. O THE OS não lê a área de "
            "transferência e não verifica semanticamente o que foi copiado."
        ),
        clipboard_effect_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_X",
        label="CTRL+X",
        modifier="CTRL",
        primary_key="X",
        risk=ActionRisk.DESTRUCTIVE,
        intent_pt="recortar",
        preview_effect=(
            "ATENÇÃO: CTRL+X pode remover o conteúdo selecionado do aplicativo e "
            "substituir o conteúdo atual da área de transferência. O THE OS não lê a "
            "área de transferência e não verifica semanticamente o que foi recortado."
        ),
        clipboard_effect_expected=True,
        content_mutation_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_V",
        label="CTRL+V",
        modifier="CTRL",
        primary_key="V",
        risk=ActionRisk.PRIVILEGED,
        intent_pt="colar",
        preview_effect=(
            "PRIVILEGIADO: CTRL+V pode inserir no aplicativo alvo o conteúdo atual da "
            "área de transferência, que pode conter dados sensíveis. O THE OS não lê, "
            "não mostra ao provedor e não pré-visualiza esse conteúdo; portanto não pode "
            "inspecionar o que será colado antes do envio."
        ),
        clipboard_used=True,
        clipboard_input_expected=True,
        content_mutation_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_Z",
        label="CTRL+Z",
        modifier="CTRL",
        primary_key="Z",
        risk=ActionRisk.DESTRUCTIVE,
        intent_pt="desfazer",
        preview_effect=(
            "ATENÇÃO: CTRL+Z pode desfazer a última operação no controle em foco e "
            "alterar, remover ou restaurar conteúdo. O THE OS não inspeciona o histórico "
            "de desfazer e não verifica semanticamente o resultado."
        ),
        content_mutation_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_F",
        label="CTRL+F",
        modifier="CTRL",
        primary_key="F",
        risk=ActionRisk.CONFIRM,
        intent_pt="buscar no conteúdo",
        preview_effect=(
            "CTRL+F pode abrir a interface de busca do aplicativo em foco. "
            "O THE OS não lê o termo pesquisado nem os resultados encontrados."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_S",
        label="CTRL+S",
        modifier="CTRL",
        primary_key="S",
        risk=ActionRisk.DESTRUCTIVE,
        intent_pt="salvar",
        preview_effect=(
            "ATENÇÃO: CTRL+S pode gravar ou sobrescrever o documento ou arquivo atual. "
            "O THE OS não inspeciona o destino, o conteúdo persistido nem confirma "
            "semanticamente o resultado do salvamento."
        ),
        content_mutation_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_Y",
        label="CTRL+Y",
        modifier="CTRL",
        primary_key="Y",
        risk=ActionRisk.DESTRUCTIVE,
        intent_pt="refazer",
        preview_effect=(
            "ATENÇÃO: CTRL+Y pode refazer uma operação anteriormente desfeita e alterar, "
            "remover ou restaurar conteúdo. O THE OS não inspeciona o histórico de refazer "
            "e não verifica semanticamente o resultado."
        ),
        content_mutation_expected=True,
    ),
    WindowShortcutSpec(
        name="CTRL_LEFT",
        label="CTRL+LEFT",
        modifier="CTRL",
        primary_key="LEFT",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar por unidade maior para a esquerda",
        preview_effect=(
            "CTRL+LEFT pode navegar para a esquerda por palavra, item ou outra unidade "
            "definida pelo controle em foco. O THE OS não inspeciona semanticamente "
            "o destino da navegação."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_RIGHT",
        label="CTRL+RIGHT",
        modifier="CTRL",
        primary_key="RIGHT",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar por unidade maior para a direita",
        preview_effect=(
            "CTRL+RIGHT pode navegar para a direita por palavra, item ou outra unidade "
            "definida pelo controle em foco. O THE OS não inspeciona semanticamente "
            "o destino da navegação."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_UP",
        label="CTRL+UP",
        modifier="CTRL",
        primary_key="UP",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar por unidade maior para cima",
        preview_effect=(
            "CTRL+UP pode navegar para cima por parágrafo, item ou outra unidade "
            "definida pelo controle em foco. O THE OS não inspeciona semanticamente "
            "o destino da navegação."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_DOWN",
        label="CTRL+DOWN",
        modifier="CTRL",
        primary_key="DOWN",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar por unidade maior para baixo",
        preview_effect=(
            "CTRL+DOWN pode navegar para baixo por parágrafo, item ou outra unidade "
            "definida pelo controle em foco. O THE OS não inspeciona semanticamente "
            "o destino da navegação."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_HOME",
        label="CTRL+HOME",
        modifier="CTRL",
        primary_key="HOME",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar para o início maior do controle",
        preview_effect=(
            "CTRL+HOME pode navegar para o início do documento, lista ou região ativa. "
            "O THE OS não inspeciona semanticamente a posição resultante."
        ),
    ),
    WindowShortcutSpec(
        name="CTRL_END",
        label="CTRL+END",
        modifier="CTRL",
        primary_key="END",
        risk=ActionRisk.CONFIRM,
        intent_pt="navegar para o fim maior do controle",
        preview_effect=(
            "CTRL+END pode navegar para o fim do documento, lista ou região ativa. "
            "O THE OS não inspeciona semanticamente a posição resultante."
        ),
    ),
)


def _build_registry() -> Mapping[str, WindowShortcutSpec]:
    registry = {spec.name: spec for spec in _WINDOW_SHORTCUT_SPECS}
    if len(registry) != len(_WINDOW_SHORTCUT_SPECS):
        raise RuntimeError("DUPLICATE_WINDOW_SHORTCUT_SPEC")

    for spec in _WINDOW_SHORTCUT_SPECS:
        if spec.modifier != "CTRL":
            raise RuntimeError(f"UNSUPPORTED_SHORTCUT_MODIFIER:{spec.name}")
        primary_is_letter = (
            len(spec.primary_key) == 1
            and "A" <= spec.primary_key <= "Z"
        )
        primary_is_registered_key = spec.primary_key in WINDOW_KEY_REGISTRY
        if not (primary_is_letter or primary_is_registered_key):
            raise RuntimeError(f"UNSUPPORTED_SHORTCUT_PRIMARY_KEY:{spec.name}")
        if spec.name != f"{spec.modifier}_{spec.primary_key}":
            raise RuntimeError(f"WINDOW_SHORTCUT_NAME_MISMATCH:{spec.name}")

    return MappingProxyType(registry)


WINDOW_SHORTCUT_REGISTRY = _build_registry()
WINDOW_SHORTCUT_SPECS: tuple[WindowShortcutSpec, ...] = tuple(
    WINDOW_SHORTCUT_REGISTRY.values()
)
ALLOWED_WINDOW_SHORTCUTS: tuple[str, ...] = tuple(WINDOW_SHORTCUT_REGISTRY)
DESTRUCTIVE_WINDOW_SHORTCUTS: frozenset[str] = frozenset(
    spec.name
    for spec in WINDOW_SHORTCUT_SPECS
    if spec.risk is ActionRisk.DESTRUCTIVE
)
PRIVILEGED_WINDOW_SHORTCUTS: frozenset[str] = frozenset(
    spec.name
    for spec in WINDOW_SHORTCUT_SPECS
    if spec.risk is ActionRisk.PRIVILEGED
)


def get_window_shortcut_spec(value: object) -> WindowShortcutSpec | None:
    if not isinstance(value, str):
        return None
    return WINDOW_SHORTCUT_REGISTRY.get(value)


def is_allowed_window_shortcut(value: object) -> bool:
    return get_window_shortcut_spec(value) is not None


def is_destructive_window_shortcut(value: object) -> bool:
    spec = get_window_shortcut_spec(value)
    return spec is not None and spec.risk is ActionRisk.DESTRUCTIVE


def is_privileged_window_shortcut(value: object) -> bool:
    spec = get_window_shortcut_spec(value)
    return spec is not None and spec.risk is ActionRisk.PRIVILEGED


def format_window_shortcut_allowlist_pt() -> str:
    labels = [spec.label for spec in WINDOW_SHORTCUT_SPECS]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " e " + labels[-1]


def build_window_shortcut_tool_description() -> str:
    operations = ", ".join(
        f"{spec.intent_pt} ({spec.label})"
        for spec in WINDOW_SHORTCUT_SPECS
    )
    confirm = ", ".join(
        spec.label
        for spec in WINDOW_SHORTCUT_SPECS
        if spec.risk is ActionRisk.CONFIRM
    )
    destructive = ", ".join(
        spec.label
        for spec in WINDOW_SHORTCUT_SPECS
        if spec.risk is ActionRisk.DESTRUCTIVE
    )
    privileged = ", ".join(
        spec.label
        for spec in WINDOW_SHORTCUT_SPECS
        if spec.risk is ActionRisk.PRIVILEGED
    )
    return (
        "Envia um atalho de teclado estritamente permitido para uma janela visível "
        "exata já conhecida por PID, título e target_token retornados pelo mesmo "
        "window_snapshot. Use somente quando o usuário pedir explicitamente uma das "
        f"operações registradas: {operations}. Classificação local atual: "
        f"CONFIRM = {confirm}; DESTRUCTIVE = {destructive}; PRIVILEGED = {privileged}. "
        "Atalhos não registrados e combinações arbitrárias permanecem bloqueados. "
        "O THE OS não lê a área de transferência nem envia seu conteúdo ao provedor."
    ) + build_hosted_window_target_guidance()
