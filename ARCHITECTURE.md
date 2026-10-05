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
6. M99: Structured Run State v1, giving LYRA explicit bounded in-memory execution
   state without adding authority or supervision.
7. M100: Verified Text File Workflow v1, deriving file-workflow state from execution
   evidence while reusing existing bounded filesystem primitives.
8. M101: Composed Workflow v1, deriving ordered cross-domain stages from M99 evidence
   while reusing specialized workflow summaries such as M100.
9. Then continue user-facing LYRA capabilities, perception, personality, voice, and
   composed workflows as concrete needs justify them.

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

## M98 - Semantic Desktop v1

M98 adds one narrow semantic desktop path without replacing the existing coordinate and
anchor engines.

The first path is `semantic_window_snapshot`. It starts from an exact, recently
observed window and enumerates native Win32 child controls from the resolved visual
frame. The result is structured control metadata rather than a screenshot or a
coordinate action.

Version 1 returns at most 32 visible native controls with:

- a class-derived semantic role;
- a bounded UI label only for native Button and Static controls;
- the native class name;
- a dialog control id when available;
- enabled state;
- an opaque process-local `control_token`.

Text editor and rich-edit values are deliberately not collected. Raw child HWND values
are never returned. The new control token is an observation reference precursor, not
an authorization grant.

`semantic_window_snapshot` requires a valid M97 window `observation_handle`, so semantic
inspection is grounded in a recent exact window observation. The handle is revalidated
locally before child-control enumeration.

The semantic source in M98 is intentionally narrow: native Win32 child-control metadata.
It does not claim full Microsoft UI Automation coverage, OCR, visual understanding, or
cross-framework accessibility support. Existing mouse, keyboard, coordinate, anchor,
and window-state tools remain unchanged and available as fallbacks when a UI does not
expose useful native controls.

M98 introduces no Phoenix authority, no new approval policy, no raw command execution,
and no rewrite of the existing Windows target resolver.

## M99 - Structured LYRA Run State v1

M99 gives LYRA an explicit in-memory representation of a tool-loop run without turning
that representation into authority, persistence, or supervision.

`LyraRunState` records:

- a process-local `run_id`;
- the normalized user goal that started the tool loop;
- lifecycle status;
- the bounded step budget and completed step count;
- the currently executing or confirmation-pending action when one exists;
- completed `RunStepState` entries containing the corresponding The Hands
  `ActionResult` evidence snapshot;
- a final provider reply or terminal error when the run ends.

The v1 lifecycle states are `RUNNING`, `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`,
and `CANCELLED`. The existing `ExecutionControl` remains the separate cooperative
pause/resume/cancel mechanism; M99 does not turn run state into an execution controller.

A `COMPLETED` run means the bounded provider/tool loop reached a final provider reply.
It does not mean that LYRA or The Hands proved the user's higher-level goal was
achieved. M96's rule remains authoritative:

    effect dispatched != goal achieved

Each completed step snapshots the concrete `ActionResult`, including evidence,
`error_code`, `effect_dispatched`, and `postcondition_verified`. The run state therefore
lets LYRA track what The Hands actually reported without manufacturing semantic success.

Confirmation pauses carry the same run identity and structured state through
`PendingActionConfirmation`, so approval resumes the same run rather than creating a
new logical execution.

The tool loop also accepts an optional observational state callback for hosts that need
structured progress. That callback grants no capability and cannot authorize an action.

M99 is intentionally process-local and ephemeral. It adds no durable run store,
cross-process recovery, background supervisor, Phoenix capability or grant, new runtime
tool, or new remote authority. Exact future actions remain provider-driven; v1 exposes
the remaining bounded step budget rather than pretending the rest of the plan is known.

## M100 - Verified Text File Workflow v1

M100 gives LYRA a structured interpretation of bounded text-file work by deriving a
`FileWorkflowState` from the M99 run evidence. It does not add a new executor or tool.

The v1 workflow recognizes these existing The Hands actions:

- observations: `inspect_path`, `read_text_file`, `read_text_lines`;
- mutations: `write_text_file`, `replace_text_literal`, `replace_text_block`.

Only resolved paths returned in The Hands `ActionResult.evidence` are used to group file
targets. Raw model arguments are not promoted into trusted workflow identity.

For each target, LYRA can now distinguish:

- successful observations before a mutation;
- successful observations after a mutation;
- attempted mutations;
- mutations that The Hands locally verified with `write_verified=True`;
- failed mutations and their latest error code;
- the latest returned SHA-256 when the concrete executor supplied one.

The derived workflow phase is `OBSERVED`, `VERIFIED`, `UNVERIFIED`, or `FAILED`.
`VERIFIED` means every recorded text-file mutation in that run carried local write
verification evidence from The Hands. It does not mean the user's higher-level goal was
proved complete.

`ToolLoopResult.file_workflow` exposes this derived state without duplicating storage.
The source of truth remains M99's immutable run steps.

LYRA's provider guidance also becomes file-workflow aware: when current file content is
needed to make a safe edit, LYRA should read the relevant content first, prefer narrow
literal replacement over whole-file rewrite when appropriate, and ground completion in
The Hands evidence such as `write_verified` and SHA-256.

M100 adds no Phoenix authority, no new approval rule, no durable workflow store, no
cross-process resume, no new runtime tool, and no filesystem primitive. Existing local
previews and mutation guards remain authoritative at the execution boundary.

## M101 - Composed Workflow v1

M101 lets LYRA derive a bounded cross-domain workflow view from the M99 run state while
reusing M100's specialized text-file workflow summary.

A composed workflow exists only when the run spans at least two action domains. Version
1 classifies completed or current actions into `APPLICATION`, `FILE`, `WINDOW`,
`PROCESS`, `SYSTEM`, `DEVELOPMENT`, or `OTHER`.

Completed actions are grouped into ordered contiguous `WorkflowStageState` values. Each
stage records its source run-step range, ordered actions, success/failure counts,
evidence-bearing step count, explicit `effect_dispatched=True` count, and explicit
`postcondition_verified=True` count. Adjacent actions in the same domain remain one
stage; a domain transition starts another stage.

A confirmation-pending or currently executing action is represented by
`current_action` and `current_domain` without pretending it has completed. This allows
the composition to become visible as soon as a run crosses into a second domain while
preserving the same M99 `run_id`.

When file actions are present, `ComposedWorkflowState.file_workflow` reuses M100's
derived `FileWorkflowState`; it does not copy or replace the underlying evidence. M99
run steps remain the source of truth.

`ToolLoopResult.composed_workflow` exposes the derived state to hosts. The provider
guidance now explicitly tells LYRA to preserve requested ordering across domains and to
base later steps and the final reply on evidence returned by prior actions.

M101 does not create a static future plan, infer unexecuted steps, grant authority,
change confirmation policy, add a supervisor, persist workflows, add cross-process
resume, or introduce a new runtime tool. A completed composed workflow still means the
bounded tool loop reached a provider reply; it is not proof that the user's higher-level
goal was achieved.
