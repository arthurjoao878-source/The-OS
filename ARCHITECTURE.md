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
