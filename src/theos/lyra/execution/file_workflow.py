from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from theos.lyra.execution.run_state import LyraRunState

FILE_WORKFLOW_VERSION = 1

_TEXT_FILE_OBSERVATION_ACTIONS = frozenset(
    {
        "inspect_path",
        "read_text_file",
        "read_text_lines",
    }
)
_TEXT_FILE_MUTATION_ACTIONS = frozenset(
    {
        "write_text_file",
        "replace_text_literal",
        "replace_text_block",
    }
)


class FileWorkflowPhase(StrEnum):
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FileTargetWorkflow:
    path: str
    observation_count: int
    mutation_count: int
    verified_mutation_count: int
    failed_mutation_count: int
    observed_before_mutation: bool
    post_mutation_observation: bool
    mutation_actions: tuple[str, ...]
    latest_sha256: str | None = None
    latest_error_code: str | None = None

    def __post_init__(self) -> None:
        normalized = self.path.strip()
        if not normalized:
            raise ValueError("file workflow path must not be blank")
        object.__setattr__(self, "path", normalized)

        counts = (
            self.observation_count,
            self.mutation_count,
            self.verified_mutation_count,
            self.failed_mutation_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("file workflow counts must not be negative")
        if self.verified_mutation_count > self.mutation_count:
            raise ValueError("verified mutations cannot exceed mutations")
        if self.failed_mutation_count > self.mutation_count:
            raise ValueError("failed mutations cannot exceed mutations")
        if len(self.mutation_actions) != self.mutation_count:
            raise ValueError("mutation action count must match mutation_count")

    @property
    def all_mutations_verified(self) -> bool:
        return (
            self.mutation_count > 0
            and self.failed_mutation_count == 0
            and self.verified_mutation_count == self.mutation_count
        )


@dataclass(frozen=True, slots=True)
class FileWorkflowState:
    phase: FileWorkflowPhase
    targets: tuple[FileTargetWorkflow, ...]
    version: int = FILE_WORKFLOW_VERSION

    def __post_init__(self) -> None:
        if self.version != FILE_WORKFLOW_VERSION:
            raise ValueError("unsupported file workflow version")
        if not self.targets:
            raise ValueError("file workflow state requires at least one target")

    @property
    def target_count(self) -> int:
        return len(self.targets)

    @property
    def mutation_count(self) -> int:
        return sum(target.mutation_count for target in self.targets)

    @property
    def verified_mutation_count(self) -> int:
        return sum(
            target.verified_mutation_count
            for target in self.targets
        )

    @property
    def failed_mutation_count(self) -> int:
        return sum(
            target.failed_mutation_count
            for target in self.targets
        )

    @property
    def all_mutations_verified(self) -> bool:
        return (
            self.mutation_count > 0
            and self.failed_mutation_count == 0
            and self.verified_mutation_count == self.mutation_count
        )


@dataclass(slots=True)
class _TargetAccumulator:
    path: str
    observation_count: int = 0
    mutation_count: int = 0
    verified_mutation_count: int = 0
    failed_mutation_count: int = 0
    observed_before_mutation: bool = False
    post_mutation_observation: bool = False
    mutation_actions: list[str] = field(default_factory=list)
    latest_sha256: str | None = None
    latest_error_code: str | None = None

    def freeze(self) -> FileTargetWorkflow:
        return FileTargetWorkflow(
            path=self.path,
            observation_count=self.observation_count,
            mutation_count=self.mutation_count,
            verified_mutation_count=self.verified_mutation_count,
            failed_mutation_count=self.failed_mutation_count,
            observed_before_mutation=self.observed_before_mutation,
            post_mutation_observation=self.post_mutation_observation,
            mutation_actions=tuple(self.mutation_actions),
            latest_sha256=self.latest_sha256,
            latest_error_code=self.latest_error_code,
        )


def _path_key(path: str) -> str:
    return path.strip().replace("/", "\\").casefold()


def summarize_file_workflow(
    run_state: LyraRunState,
) -> FileWorkflowState | None:
    accumulators: dict[str, _TargetAccumulator] = {}

    for step in run_state.steps:
        if (
            step.action not in _TEXT_FILE_OBSERVATION_ACTIONS
            and step.action not in _TEXT_FILE_MUTATION_ACTIONS
        ):
            continue

        raw_path = step.evidence.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue

        key = _path_key(raw_path)
        accumulator = accumulators.get(key)
        if accumulator is None:
            accumulator = _TargetAccumulator(path=raw_path.strip())
            accumulators[key] = accumulator

        if step.action in _TEXT_FILE_OBSERVATION_ACTIONS:
            if not step.success:
                continue
            accumulator.observation_count += 1
            if accumulator.mutation_count == 0:
                accumulator.observed_before_mutation = True
            else:
                accumulator.post_mutation_observation = True
            continue

        accumulator.mutation_count += 1
        accumulator.mutation_actions.append(step.action)

        if not step.success:
            accumulator.failed_mutation_count += 1
            accumulator.latest_error_code = step.error_code
            continue

        if step.evidence.get("write_verified") is True:
            accumulator.verified_mutation_count += 1

        sha256 = step.evidence.get("sha256")
        if isinstance(sha256, str) and sha256.strip():
            accumulator.latest_sha256 = sha256.strip()

    if not accumulators:
        return None

    targets = tuple(
        accumulator.freeze()
        for accumulator in accumulators.values()
    )
    mutation_count = sum(target.mutation_count for target in targets)
    verified_count = sum(
        target.verified_mutation_count
        for target in targets
    )
    failed_count = sum(
        target.failed_mutation_count
        for target in targets
    )

    if failed_count:
        phase = FileWorkflowPhase.FAILED
    elif mutation_count == 0:
        phase = FileWorkflowPhase.OBSERVED
    elif verified_count == mutation_count:
        phase = FileWorkflowPhase.VERIFIED
    else:
        phase = FileWorkflowPhase.UNVERIFIED

    return FileWorkflowState(
        phase=phase,
        targets=targets,
    )
