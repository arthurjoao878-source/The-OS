# LYRA / TheOS Architecture

This document is the architectural reference from M94R onward.

## Identity

- **LYRA** is the portable personal assistant: it converses, understands, remembers,
  plans, requests capabilities, observes results, and explains them to the user.
- **TheOS** is the current host that provides local and Windows capabilities to LYRA.
- **Phoenix OS** is a future multi-agent orchestration system. It is not LYRA and it is
  not a dependency of TheOS.

The central rule is:

> LYRA does not control Windows because it is TheOS. LYRA requests capabilities from
> its host. Today that host is TheOS; a future host may be Phoenix OS.

## Architectural direction

Portability should be achieved incrementally. M94R deliberately does **not** introduce
a large host abstraction, plugin system, policy engine, parallel registries, service
locator, or Phoenix-specific infrastructure.

The migration rule is:

1. keep the current system usable;
2. introduce the smallest interface only when a real consumer needs it;
3. adapt one real execution path;
4. prove existing behavior still works;
5. continue incrementally.

## Responsibility classes

### CORE_ASSISTANT

Conversation, context, memory semantics, planning, task execution, personality,
perception, voice, and the future minimal host-facing capability contract belong to
LYRA.

### THEOS_HOST

Windows adapters and local capabilities belong to TheOS: applications, windows,
mouse, keyboard, files, processes, and system state. The current ActionRegistry and
ToolCatalog remain host implementation details until a smaller host port is introduced.

### DEVELOPMENT_ONLY

Git operations, GitHub delivery workflows, Python syntax checking, Ruff, pytest,
development harnesses, CI, and evidence scripts are development infrastructure.
They are not part of the normal LYRA runtime profile.

### OPTIONAL_CAPABILITY_PACK

A development-only capability may later become an optional runtime pack when there is
a deliberate user-facing need, for example repository work. That promotion must be
explicit; it is not implied by the tool existing in this repository.

### LEGACY_SUPERSEDED

The old M94 push-candidate work remains valid historical work but is superseded by
this architecture direction. Its local commit is preserved separately and must not be
published merely because it passed its earlier technical checks.

## Runtime profiles

The normal LYRA runtime exposes only assistant-facing capabilities. Development tools
remain implemented and testable, but are not advertised to the model in the normal
assistant process.

This separation means:

    tools used to build/test/version LYRA
    !=
    capabilities LYRA receives at runtime

M94R changes exposure and responsibility only. It must not reduce already working
Windows functionality.

## Security

Security is proportional to concrete risk.

- READ_ONLY: normally executes.
- NORMAL: executes.
- CONFIRM: meaningful action or sensitive-information exposure.
- DESTRUCTIVE: confirms.
- PRIVILEGED: confirms.

Existing risk behavior is intentionally left unchanged by M94R. Later usability work
may simplify excessive confirmations capability-by-capability, based on concrete harm
rather than formal authority for its own sake.

## Near-term roadmap

1. M94R: runtime/development profile separation and architecture recalibration.
2. M95: one minimal host/capability port, introduced only around a real execution path.
3. M96: configurable task-loop budget, deadline, simple repetition detection, progress,
   cancellation, and clear failure.
4. M97+: Windows usability/reliability, file workflows, context/perception,
   personality, voice, and composed user workflows.

The project should return quickly to user-facing assistant capability after the minimum
portability seam is established.
