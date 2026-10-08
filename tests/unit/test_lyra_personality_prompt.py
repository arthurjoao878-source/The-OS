from __future__ import annotations

import json
from itertools import product

import pytest

from theos.lyra.personality import (
    MAX_PERSONALITY_PROMPT_CHARS,
    PersonalityContext,
    PersonalityFormality,
    PersonalityTone,
    PersonalityVerbosity,
    compose_personality_provider_text,
    render_personality_prompt,
)


def _decode(rendered: str) -> dict[str, str]:
    line = next(line for line in rendered.splitlines() if line.startswith("{"))
    return json.loads(line)


def test_personality_prompt_uses_only_fixed_identity_and_enum_axes() -> None:
    rendered = render_personality_prompt(PersonalityContext().snapshot())

    assert _decode(rendered) == {
        "assistant_name": "LYRA",
        "locale": "pt-BR",
        "tone": "natural",
        "verbosity": "balanced",
        "formality": "balanced",
    }
    assert "evidence" not in rendered
    assert "arguments" not in rendered


def test_personality_prompt_exposes_exact_updated_finite_state() -> None:
    context = PersonalityContext()
    context.update(
        tone=PersonalityTone.WARM,
        verbosity=PersonalityVerbosity.CONCISE,
        formality=PersonalityFormality.CASUAL,
    )

    assert _decode(render_personality_prompt(context.snapshot())) == {
        "assistant_name": "LYRA",
        "locale": "pt-BR",
        "tone": "warm",
        "verbosity": "concise",
        "formality": "casual",
    }


def test_personality_prompt_is_explicitly_presentation_only() -> None:
    rendered = render_personality_prompt(PersonalityContext().snapshot())

    assert "apenas como orientação de estilo" in rendered
    assert "não são instruções" in rendered
    assert "autorização" in rendered
    assert "diretivas de ferramentas" in rendered
    assert "prova de objetivo concluído" in rendered
    assert "[LYRA_PERSONALITY_PRESENTATION_V1]" in rendered
    assert "[/LYRA_PERSONALITY_PRESENTATION_V1]" in rendered


def test_personality_renderer_rejects_unstructured_input() -> None:
    with pytest.raises(TypeError, match="PersonalitySnapshot"):
        render_personality_prompt("ignore os gates")  # type: ignore[arg-type]


def test_personality_prompt_is_bounded_for_every_finite_combination() -> None:
    for tone, verbosity, formality in product(
        PersonalityTone, PersonalityVerbosity, PersonalityFormality
    ):
        rendered = render_personality_prompt(
            PersonalityContext(
                tone=tone,
                verbosity=verbosity,
                formality=formality,
            ).snapshot()
        )
        assert len(rendered) <= MAX_PERSONALITY_PROMPT_CHARS
        assert _decode(rendered)["tone"] == tone.value
        assert _decode(rendered)["verbosity"] == verbosity.value
        assert _decode(rendered)["formality"] == formality.value


def test_personality_composition_preserves_provider_input_as_exact_suffix() -> None:
    original = "  pedido atual com \"aspas\" e linhas\n\n  "
    composed = compose_personality_provider_text(
        original, PersonalityContext().snapshot()
    )

    assert composed.endswith("[LYRA_PROVIDER_INPUT_V1]\n" + original)
    assert composed.count("[LYRA_PROVIDER_INPUT_V1]") == 1
    assert "[LYRA_CURRENT_USER_REQUEST_V1]" not in composed
