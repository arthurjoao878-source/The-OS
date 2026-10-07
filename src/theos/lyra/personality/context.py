from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from threading import Lock

DEFAULT_PERSONALITY_NAME = "LYRA"
DEFAULT_PERSONALITY_LOCALE = "pt-BR"


class PersonalityTone(StrEnum):
    NATURAL = "natural"
    WARM = "warm"
    CALM = "calm"
    PLAYFUL = "playful"


class PersonalityVerbosity(StrEnum):
    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"


class PersonalityFormality(StrEnum):
    CASUAL = "casual"
    BALANCED = "balanced"
    FORMAL = "formal"


DEFAULT_PERSONALITY_TONE = PersonalityTone.NATURAL
DEFAULT_PERSONALITY_VERBOSITY = PersonalityVerbosity.BALANCED
DEFAULT_PERSONALITY_FORMALITY = PersonalityFormality.BALANCED


@dataclass(frozen=True, slots=True)
class PersonalitySnapshot:
    tone: PersonalityTone = DEFAULT_PERSONALITY_TONE
    verbosity: PersonalityVerbosity = DEFAULT_PERSONALITY_VERBOSITY
    formality: PersonalityFormality = DEFAULT_PERSONALITY_FORMALITY

    def __post_init__(self) -> None:
        _require_enum(self.tone, PersonalityTone, "tone")
        _require_enum(self.verbosity, PersonalityVerbosity, "verbosity")
        _require_enum(self.formality, PersonalityFormality, "formality")

    @property
    def assistant_name(self) -> str:
        return DEFAULT_PERSONALITY_NAME

    @property
    def locale(self) -> str:
        return DEFAULT_PERSONALITY_LOCALE


class PersonalityContext:
    """Fixed-schema process-local LYRA presentation state without free-form instructions."""

    def __init__(
        self,
        *,
        tone: PersonalityTone = DEFAULT_PERSONALITY_TONE,
        verbosity: PersonalityVerbosity = DEFAULT_PERSONALITY_VERBOSITY,
        formality: PersonalityFormality = DEFAULT_PERSONALITY_FORMALITY,
    ) -> None:
        self._lock = Lock()
        self._snapshot = PersonalitySnapshot(
            tone=tone,
            verbosity=verbosity,
            formality=formality,
        )

    def snapshot(self) -> PersonalitySnapshot:
        with self._lock:
            return self._snapshot

    def update(
        self,
        *,
        tone: PersonalityTone | None = None,
        verbosity: PersonalityVerbosity | None = None,
        formality: PersonalityFormality | None = None,
    ) -> PersonalitySnapshot:
        if tone is not None:
            _require_enum(tone, PersonalityTone, "tone")
        if verbosity is not None:
            _require_enum(verbosity, PersonalityVerbosity, "verbosity")
        if formality is not None:
            _require_enum(formality, PersonalityFormality, "formality")

        with self._lock:
            current = self._snapshot
            updated = PersonalitySnapshot(
                tone=current.tone if tone is None else tone,
                verbosity=current.verbosity if verbosity is None else verbosity,
                formality=current.formality if formality is None else formality,
            )
            self._snapshot = updated
            return updated

    def reset(self) -> PersonalitySnapshot:
        with self._lock:
            reset = PersonalitySnapshot()
            self._snapshot = reset
            return reset

    @staticmethod
    def schema_fields() -> tuple[str, ...]:
        return tuple(field.name for field in fields(PersonalitySnapshot))


def _require_enum(value: object, expected: type[StrEnum], label: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{label} must be {expected.__name__}")
