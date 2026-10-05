# LYRA / THE HANDS / PHOENIX Architecture

This document is the canonical architectural reference from M95R onward.

## Canonical separation

The ecosystem permanently separates intelligence, authority, and execution:

    LYRA
    intelligence / interpretation / reasoning / planning / context
        |
        v
    PHOENIX
    authority / policy / capabilities / grants / orchestration
        |
        v
    THE HANDS
    concrete local execution / observation / evidence

The permanent rule is:

    Intelligence != Authority != Execution

Or, more compactly:

    Lyra thinks.
    Phoenix governs.
    The Hands acts.

LYRA, Phoenix, and The Hands are distinct responsibilities. One component must not
silently absorb the responsibility of another.

## Identity and migration

The project previously called The OS is now conceptually **The Hands**.

Legacy names such as the `theos` Python package, the repository name, local paths,
environment-variable prefixes, test names, and historical documentation may remain
temporarily when renaming them would create unnecessary risk. Their continued presence
is compatibility debt, not the architectural identity of the system.

Do not perform a cosmetic repository-wide rename merely to remove the old spelling.
Migration must remain incremental and behavior-preserving.

## LYRA

LYRA is the personal intelligence layer. It owns:

- understanding the user's intent;
- relevant personal context and memory semantics;
- reasoning and planning;
- task decomposition;
- tracking the user's goal;
- interpreting observations and evidence;
- communicating with the user.

LYRA proposes what it wants to accomplish. A proposal is not permission.

LYRA must not implicitly own system authority, approval policy, unrestricted computer
access, Windows transport code, or local execution primitives.

The current planner and tool loop still contain legacy direct-execution coupling. That
coupling is migration debt and must not be expanded while the Phoenix boundary does not
yet exist.

## PHOENIX

Phoenix is the authority and orchestration layer.

Its future responsibilities include policy, capability grants, execution envelopes,
delegation, approvals, orchestration, and multi-agent coordination.

Those responsibilities are **not implemented inside LYRA or The Hands merely to prepare
for Phoenix**. Phoenix 0.40+ will introduce them deliberately in the Phoenix project.

No Capability Registry, Capability Grants system, Phoenix policy engine, remote
approval system, durable supervisor, or MCP authority layer belongs in this repository
as part of M95R.

## THE HANDS

The Hands is the concrete local execution layer:

> execute this bounded operation and report exactly what happened.

It owns local execution and observation domains such as:

- applications;
- windows;
- keyboard;
- mouse;
- filesystem;
- processes;
- local system inspection;
- future accessibility / semantic UI;
- future bounded command execution.

The Hands is not an LLM, planner, autonomous agent, policy engine, authorization
service, personal memory system, or supervisor.

Technical validation remains appropriate inside The Hands. It may reject malformed,
unsupported, stale, ambiguous, or technically unsafe execution inputs. That is
different from deciding whether an actor is authorized to perform an otherwise valid
operation.

## Semantic-first desktop direction

Desktop interaction should evolve toward:

    native / system API
        |
        v
    accessibility / semantic UI
        |
        v
    structured observation
        |
        v
    visual reference
        |
        v
    coordinate fallback

Existing coordinate and anchor engines remain valid fallbacks and must not be rewritten
merely to satisfy this direction.

## Observation references

The existing window `target_token` is useful and remains supported. It is a precursor
to future structured, ephemeral observation references.

A later Observation Handle may carry fields such as observation id, resource,
element reference, observation time, expiry, and version. That work is deferred until a
real consumer needs it.

References must eventually be treated as observations of state, not eternal identities.

## Execution evidence

The Hands must preserve the distinction:

    effect dispatched != goal achieved

A local executor may prove that an input event was sent, a process launch was
dispatched, or a window state changed. It must not automatically claim that the user's
higher-level objective was achieved.

The current `ActionResult` remains for compatibility. Future execution-result work will
gradually distinguish effect dispatch, postcondition verification, observations,
artifacts, stdout/stderr/exit status where relevant, and errors.

## Current local approval bridge

The repository currently contains `ActionRisk`, `requires_confirmation`,
confirmation previews, and local confirmation UI. They remain active so existing
behavior and safety do not regress before Phoenix is integrated.

Their architectural status from M95R onward is:

    LEGACY_LOCAL_APPROVAL_BRIDGE

This bridge is compatibility infrastructure, not the final authority model.

Do not expand it into a larger policy system inside The Hands. Future authorization
logic belongs to Phoenix. Technical execution validation and bounded local safeguards
may remain in The Hands.

## Development tooling

Git operations, GitHub delivery, pytest, Ruff, Python syntax/static checks, CI, and
development harnesses remain development infrastructure.

    tools used to build/test/version the project
    !=
    runtime authority
    !=
    normal LYRA capabilities

The M94R assistant/development runtime-profile separation remains valid.

## Superseded work

- Old M94 push-candidate work remains archived locally and unpublished.
- The attempted M95 Minimal Capability Host is superseded before commit.
- Do not reintroduce a LYRA-facing host port that combines policy lookup and execution
  merely to hide `ActionRegistry` behind another name.

A future boundary should be introduced only when its real producer and consumer are
clear.

## Near-term roadmap

1. M94R: runtime/development profile separation - CLOSED.
2. M95R: canonical LYRA / Phoenix / The Hands boundary realignment.
3. M96: The Hands Execution Result v1, compatibly separating dispatched effect from
   verified postcondition/evidence.
4. M97: Observation Handle v1, evolving current target-token semantics without a
   rewrite.
5. M98: Semantic Desktop v1, adding one real accessibility/semantic path while keeping
   coordinate interaction as fallback.
6. Then continue user-facing LYRA capabilities, structured run state, file workflows,
   perception, personality, voice, and composed workflows as concrete needs justify
   them.

The project must remain usable throughout the migration.

## M96 - The Hands Execution Result v1

M96 begins a compatible migration from one overloaded `success` flag toward explicit
execution evidence.

`ActionResult` now carries two optional fields:

- `effect_dispatched`: whether this execution boundary can positively establish that
  the concrete local effect was dispatched;
- `postcondition_verified`: whether this boundary positively verified its declared
  local postcondition.

Both default to `None`. Existing actions therefore remain compatible and do not invent
evidence they do not yet produce. The legacy `success` field remains unchanged for
callers during migration and must not be interpreted as proof that the user's
higher-level goal was achieved.

M96 migrates two representative execution paths only:

- `open_application`: a returned launch PID establishes dispatch; process verification
  separately establishes or rejects the local postcondition;
- `maximize_window`: when the exact target is already maximized, the postcondition may
  be verified without dispatching a new maximize effect. Otherwise successful
  maximization records both dispatch and verified postcondition.

This milestone does not introduce Phoenix authority, change risk/confirmation policy,
rewrite Windows adapters, add Observation Handles, or claim semantic application
effects that are not observed.

The migration rule for later actions is evidence-first: populate these fields only when
the current execution boundary can establish them from real local control flow or
verification evidence.

## M97 - Window Observation Handle v1

M97 evolves the existing process-local `target_token` into a structured, ephemeral
observation reference without removing or replacing the token.

Each window returned by `window_snapshot` and `window_snapshot_many` now also carries
an `observation_handle` containing:

- `version`;
- `observation_id`;
- `resource`;
- `element_ref`;
- `observed_at`;
- `expires_at`;
- `signature`.

The v1 window handle is short lived, signed with a process-local secret, bound to the
existing `target_token`, and invalid after the process restarts because a new local
secret is generated. It is evidence of a recent observation, not an authorization
grant.

`maximize_window` is the first consumer migrated to understand the handle. When the
model forwards a handle from the selected snapshot row, the tool catalog and action
validate its structure, signature, freshness, and binding before execution. The action
revalidates the handle immediately before entering the existing Windows execution path.

For the strict AI tool surface, `observation_handle` is required but nullable: the
model forwards the handle object when the selected snapshot row has one and uses `null`
for legacy contexts without a handle. Internally, the legacy token-only maximize path
remains accepted during migration. No other window action is forced to consume
observation handles yet.

The existing Windows target resolution remains authoritative for the concrete local
window identity. M97 does not expose raw HWND values, create a handle registry, add
Phoenix authority, change confirmation policy, or rewrite the Windows engine.

Future milestones may migrate additional consumers and refine stale-reference behavior
only when a real workflow requires it.
