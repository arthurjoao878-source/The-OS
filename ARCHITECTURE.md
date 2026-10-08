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
9. M102: Structured Workflow Progress v1, deriving compact live progress snapshots
   from M99/M100/M101 evidence without adding execution semantics.
10. M103: Host Workflow Progress v1, presenting the M102 state stream in the desktop
    host without adding authority or execution behavior.
11. M104: Native Semantic Button Invoke v1, consuming an exact M98 control token for
    one bounded Win32 Button action before coordinate fallback.
12. M105: Native Semantic Edit Text v1, setting one exact native Edit value with
    local postcondition verification before keyboard or coordinate fallback.
13. M106: Native Semantic Checkbox State v1, setting one exact BS_AUTOCHECKBOX state
    idempotently with native readback verification before coordinate fallback.
14. M107: Native Semantic Combo Box Selection v1, setting one exact native ComboBox
    index idempotently with CB_GETCURSEL readback before coordinate fallback.
15. M108: Native Semantic ListBox Selection v1, setting one exact single-selection
    native ListBox index idempotently with LB_GETCURSEL readback before coordinate fallback.
16. M109: Native Semantic Radio Button Select v1, selecting one exact native
    BS_AUTORADIOBUTTON idempotently with BM_GETCHECK readback before coordinate fallback.
17. M110: Native Semantic Tab Control Selection v1, setting one exact SysTabControl32
    selected index idempotently with TCM_GETCURSEL readback before coordinate fallback.
18. M111: Bounded LYRA Perception Context v1, retaining only bounded process-local
    summaries of verified The Hands action results without copying raw evidence or arguments.
19. M112: Bounded LYRA Perception Prompt Exposure v1, exposing only bounded perception
    summaries to the provider while preserving raw user intent for local authority gates.
20. M113: Bounded LYRA Personality Context v1, keeping process-local presentation style
    in a fixed finite schema without free-form instructions or authority-bearing fields.
21. M114: Bounded LYRA Personality Prompt Exposure v1, applying finite presentation
    preferences at provider request entry without granting tool or policy authority.
22. M115: Bounded LYRA Personality Host Controls v1, allowing finite process-local
    presentation settings in the desktop UI without changing authority.
23. M116: Bounded LYRA Conversation History Exposure v1, applying finite limits to prior
    conversation turns passed to the provider without altering the current user request.
24. M117: Explicit LYRA Session Reset Host Control v1, allowing a confirmed
    user-initiated clear of process-local conversation and perception state.
25. M118: Bounded LYRA Context Visibility Host v1, displaying only process-local
    counts for M116 provider history and M111 perception, without new authority.
26. Then continue user-facing LYRA capabilities, voice, and composed workflows as
    concrete needs justify them.

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

## M102 - Structured Workflow Progress v1

M102 derives a compact, host-facing workflow progress snapshot from the M99 run state.
It does not introduce another source of execution state.

`WorkflowProgressState` identifies whether a run is newly started, actively executing
an action, awaiting confirmation, between completed steps, completed, failed, or
cancelled. The snapshot carries the bounded step budget, current action/domain when one
exists, latest completed action/domain, latest step success/error code, the ordered
domain sequence observed so far, and the current M100 file-workflow phase when relevant.

Domain transitions are derived from completed M99 steps plus the current action. This
means a second domain becomes visible while that action is current or awaiting
confirmation, without pretending the action has completed.

`ToolLoopResult.workflow_progress` exposes the derived snapshot. Existing M99 state
callbacks remain the source of live state events; hosts can derive this progress view
from each callback without changing execution semantics.

M102 adds no future-plan inference, no persistence, no supervisor, no new authority,
no new confirmation rule, no cross-process resume, and no runtime tool. Progress is an
interpretation of already-recorded run evidence, not proof that the user's higher-level
goal was achieved.

## M103 - Host Workflow Progress v1

M103 makes the desktop host consume the M102 run-state stream and present a compact
workflow status line to the user.

The tool-loop worker and confirmation-resume worker forward the existing M99 state
callback through a Qt signal. The main window converts each received `LyraRunState`
into the M102 `WorkflowProgressState` and then into a host-only presentation view.

The host status line distinguishes started, running, awaiting-confirmation,
step-completed, completed, failed, and cancelled states. When an action is current or a
step has completed, it also surfaces the concrete action name, bounded step count, and
its M101 domain using user-facing labels.

The presentation adapter is deliberately separate from execution. It cannot approve,
reject, resume, cancel, reorder, or synthesize actions. Existing confirmation dialogs
and `ExecutionControl` remain unchanged. The state signal is observational only.

M103 adds no authority, no new execution primitive, no runtime tool, no durable progress
store, no cross-process resume, and no future-plan inference. The displayed completion
state means the bounded LYRA tool loop reached its terminal run state; it does not prove
the user's higher-level goal was achieved.

## M104 - Native Semantic Button Invoke v1

M104 gives the M98 semantic desktop path its first direct execution consumer:
`invoke_semantic_button`.

The action accepts only an exact, recently observed window plus an exact Button row from
`semantic_window_snapshot`. The request carries the M97 window observation handle, the
window target token, the process and title, and the semantic control token together with
the Button metadata that was presented to the model.

Before dispatch, The Hands revalidates the signed window observation, resolves the exact
window again, enumerates its native Win32 child controls again, and requires one visible,
enabled `Button` whose recomputed opaque token, bounded name, and control id still match
the approved row. Stale, changed, hidden, disabled, non-button, missing, or ambiguous
controls fail closed.

The concrete invocation uses bounded `SendMessageTimeoutW(BM_CLICK)` rather than cursor
coordinates. A successful dispatch records `effect_dispatched=True`; it deliberately
does not claim that the application's internal semantic outcome or the user's
higher-level goal was verified. Existing coordinate and anchor tools remain fallbacks
for interfaces that do not expose a usable native Button.

`invoke_semantic_button` remains behind the existing local confirmation bridge. Its
preview binds the exact window observation and semantic control metadata into an
execution guard before the effect is allowed. This is still compatibility approval
infrastructure, not Phoenix authority.

M104 adds one normal-runtime The Hands tool and no development-only tool. It adds no
Phoenix policy, grant, supervisor, durable control registry, raw HWND exposure, OCR,
cross-process resume, or general UI Automation framework.

## M105 - Native Semantic Edit Text v1

M105 extends the M98 semantic desktop path from native Button invocation to one narrow
text-editing primitive: `set_semantic_text`.

Version 1 accepts only an exact native Win32 `Edit` row returned by
`semantic_window_snapshot`. The request carries the recent M97 window observation, the
window target token, the M98 semantic control token, the exact control id and the text
approved by the user-facing confirmation bridge.

Before mutation, The Hands revalidates the signed window observation, resolves the
exact window again, enumerates native child controls again, recomputes the semantic
control token, and requires exactly one visible, enabled `Edit` with the same control
id. Password and read-only Edit styles fail closed. RichEdit and other text-editor
classes remain unsupported in this first consumer.

The concrete mutation uses bounded `SendMessageTimeoutW(WM_SETTEXT)` and does not move
the cursor, synthesize keyboard input, use the clipboard, or expose a raw HWND. The
approved value is then read back locally with bounded WM_GETTEXT messages and compared
for exact equality. Evidence reports only length and SHA-256 of the approved value, not
the read-back text itself.

A successful M105 action therefore records both `effect_dispatched=True` and
`postcondition_verified=True` for the local Edit value. This remains a concrete
postcondition, not proof that the user's higher-level application goal was achieved.

`set_semantic_text` stays behind the existing `LEGACY_LOCAL_APPROVAL_BRIDGE`; its
preview binds the exact window observation, semantic control token, control id, and
SHA-256 of the approved text. M105 adds no Phoenix policy, grant, durable control
registry, raw HWND exposure, OCR, general UI Automation framework, or cross-process
resume. Existing `type_text` and coordinate/anchor actions remain fallbacks when a
usable native Edit is unavailable.

## M106 - Native Semantic Checkbox State v1

M106 extends the M98 semantic desktop path with one narrow idempotent state-setting
primitive: `set_semantic_checkbox_state`.

Version 1 accepts the exact native Win32 `Button` row returned by
`semantic_window_snapshot`, but execution fails closed unless the revalidated native
style is `BS_AUTOCHECKBOX`. Push buttons, radio buttons, three-state checkboxes and
other Button styles remain unsupported by this first checkbox consumer.

The request carries the recent M97 window observation, the window target token, the M98
semantic control token, the bounded Button name, exact control id and the desired
boolean checked state. The existing local confirmation preview binds all of those
values before execution.

Before any mutation, The Hands revalidates the signed window observation, resolves the
exact window again, enumerates native child controls again, recomputes the semantic
control token and requires exactly one visible, enabled matching Button. The current
checkbox state is then read through bounded `SendMessageTimeoutW(BM_GETCHECK)`.

If the checkbox already equals the approved state, M106 dispatches no click and reports
`effect_dispatched=False` with `postcondition_verified=True`. Otherwise it dispatches
one bounded native `BM_CLICK`, reads the state again with `BM_GETCHECK`, and requires
exact equality with the approved state. A dispatched click whose postcondition cannot
be verified is reported as dispatched but unverified rather than as success.

M106 does not move the cursor, synthesize keyboard input, use the clipboard, expose raw
HWND values or claim that the user's higher-level application goal was achieved.
Existing `invoke_semantic_button`, keyboard and coordinate actions remain available for
interfaces outside this narrow native checkbox path. M106 adds no Phoenix policy,
grant, supervisor, durable registry, OCR, general UI Automation framework or
cross-process resume.

## M107 - Native Semantic Combo Box Selection v1

M107 extends the M98 semantic desktop path with one narrow idempotent ComboBox
selection primitive: `set_semantic_combo_box_index`.

Version 1 accepts only the exact native Win32 `ComboBox` row returned by
`semantic_window_snapshot`. The request carries the recent M97 window observation,
window target token, M98 semantic control token, exact control id and a zero-based
desired item index. ComboBoxEx and other combo frameworks remain unsupported in v1.

Before mutation, The Hands revalidates the signed window observation, resolves the
exact window again, enumerates native child controls again, recomputes the semantic
control token and requires exactly one visible, enabled matching native `ComboBox`.
It reads the item count with bounded `SendMessageTimeoutW(CB_GETCOUNT)` and fails
closed when the requested index is outside that concrete local range.

The current selection is read with `CB_GETCURSEL`. If it already equals the approved
index, no selection message is dispatched and the action reports
`effect_dispatched=False` with `postcondition_verified=True`. Otherwise one bounded
`CB_SETCURSEL` is sent and `CB_GETCURSEL` must read back the exact approved index.
A dispatched selection whose local postcondition cannot be verified is reported as
dispatched but unverified rather than as success.

M107 deliberately does not enumerate or return ComboBox item text, move the cursor,
synthesize keyboard input, use the clipboard or expose raw HWND values. `CB_SETCURSEL`
proves only the local control selection; v1 does not claim that an application-level
selection-change notification was observed or that the user's higher-level goal was
achieved. Existing keyboard and coordinate actions remain fallbacks when an exact
index is not known or a usable native ComboBox is unavailable. M107 adds no Phoenix
policy, grant, supervisor, durable registry, OCR, general UI Automation framework or
cross-process resume.

## M108 - Native Semantic ListBox Selection v1

M108 extends the M98 semantic desktop path with one narrow idempotent ListBox
selection primitive: `set_semantic_list_box_index`.

Version 1 accepts only the exact native Win32 `ListBox` row returned by
`semantic_window_snapshot`. The request carries the recent M97 window observation,
window target token, M98 semantic control token, exact control id and a zero-based
desired item index. `SysListView32`, owner-specific list frameworks and other list
controls remain unsupported in v1.

Before mutation, The Hands revalidates the signed window observation, resolves the
exact window again, enumerates native child controls again, recomputes the semantic
control token and requires exactly one visible, enabled matching native `ListBox`.
The adapter reads the native style and fails closed when `LBS_MULTIPLESEL` or
`LBS_EXTENDEDSEL` is present, because this v1 models only single-selection state.

For a supported single-selection ListBox, The Hands reads the item count with bounded
`SendMessageTimeoutW(LB_GETCOUNT)` and fails closed when the requested index is outside
that concrete local range. The current selection is read with `LB_GETCURSEL`. If it
already equals the approved index, no selection message is dispatched and the action
reports `effect_dispatched=False` with `postcondition_verified=True`. Otherwise one
bounded `LB_SETCURSEL` is sent and `LB_GETCURSEL` must read back the exact approved
index. A dispatched selection whose local postcondition cannot be verified is reported
as dispatched but unverified rather than as success.

M108 deliberately does not enumerate or return ListBox item text, move the cursor,
synthesize keyboard input, use the clipboard or expose raw HWND values. `LB_SETCURSEL`
proves only the local single-selection control state; v1 does not claim that an
application-level selection-change notification was observed or that the user's
higher-level goal was achieved. Existing keyboard and coordinate actions remain
fallbacks when an exact index is not known, selection is multiple, or a usable native
ListBox is unavailable. M108 adds no Phoenix policy, grant, supervisor, durable
registry, OCR, general UI Automation framework or cross-process resume.

## M109 - Native Semantic Radio Button Select v1

M109 extends the M98 semantic desktop path with one narrow idempotent native radio
selection primitive: `select_semantic_radio_button`.

Version 1 accepts the exact native Win32 `Button` row returned by
`semantic_window_snapshot`, but execution fails closed unless the revalidated native
style is `BS_AUTORADIOBUTTON`. Manual `BS_RADIOBUTTON`, checkboxes, push buttons and
other Button styles remain unsupported by this first radio consumer.

The request carries the recent M97 window observation, the window target token, the M98
semantic control token, the bounded Button name and exact control id. There is no
desired boolean argument: M109 only means "select this exact radio button". It does not
offer a semantic operation for directly unchecking a radio button.

Before mutation, The Hands revalidates the signed window observation, resolves the exact
window again, enumerates native child controls again, recomputes the semantic control
token and requires exactly one visible, enabled matching Button. The current target
state is read through bounded `SendMessageTimeoutW(BM_GETCHECK)`.

If the target radio is already checked, M109 dispatches no click and reports
`effect_dispatched=False` with `postcondition_verified=True`. Otherwise it dispatches
one bounded native `BM_CLICK`, reads the target again with `BM_GETCHECK`, and requires
the exact target to be checked. A dispatched click whose target postcondition cannot be
verified is reported as dispatched but unverified rather than as success.

M109 deliberately verifies only the selected target. It does not enumerate native radio
group boundaries or claim that sibling exclusivity was independently verified, even
though `BS_AUTORADIOBUTTON` supplies native group behavior when the application is
configured correctly. The action does not move the cursor, synthesize keyboard input,
use the clipboard, expose raw HWND values or claim that the user's higher-level goal
was achieved. Existing button, keyboard and coordinate actions remain fallbacks for
unsupported radio styles. M109 adds no Phoenix policy, grant, supervisor, durable
registry, OCR, general UI Automation framework or cross-process resume.

## M110 - Native Semantic Tab Control Selection v1

M110 extends the M98 native semantic desktop path with one idempotent tab-selection
primitive: `set_semantic_tab_index` for an exact native Win32 `SysTabControl32`.

The user-supplied exact zero-based index is bound to a recent window observation,
opaque target/control tokens, the native tab control id, and the existing local
confirmation preview. The Hands revalidates the exact window and control and rejects
stale, missing, ambiguous, hidden, disabled or non-Tab controls before mutation.

The v1 reads a bounded `TCM_GETITEMCOUNT` and requires a valid current selection
from `TCM_GETCURSEL`. Unsupported no-selection, out-of-range targets, and ambiguous
control state fail closed. If the approved index is already active, it reports
`effect_dispatched=False` with `postcondition_verified=True` without dispatching.
Otherwise, one bounded `TCM_SETCURSEL` must return the exact *previous* index; then
`TCM_GETCURSEL` must return the exact approved index. A dispatched mutation whose
readback cannot be proven is reported as dispatched but unverified.

`TCM_SETCURSEL` does not prove the host application processed tab selection-change
notifications or updated a corresponding page. M110 verifies only native local tab
selection state, not visible page contents, item text, application behavior or the
user's higher-level goal. It does not move the cursor, synthesize keyboard input,
read tab labels, use clipboard, or expose raw HWND values. Existing coordinate and
keyboard operations remain fallbacks when a usable native tab is unavailable.

M110 creates no Phoenix policy/grant, agent authority, durable store, supervisor,
OCR, cross-process resume, or general UI Automation framework.


## M111 - Bounded LYRA Perception Context v1

M111 begins the post-semantic-control LYRA phase with a bounded process-local perception
context. The context records only a compact summary after The Hands returns an
`ActionResult`: action name, success, bounded visible message, error code, dispatched
effect evidence and verified local postcondition evidence.

The perception buffer deliberately does not copy action arguments or the raw `evidence`
mapping. This keeps file contents, HWND-like implementation data, tool-specific payloads
and other potentially sensitive evidence out of the new cross-turn perception object.
The buffer is capped, evicts oldest observations, can be explicitly cleared, and is lost
on process restart. It is separate from `SessionContext` and persistent SQLite memory.

The existing tool loop may record action results into this context, and the assistant
host owns one context for its process lifetime. M111 does not yet inject perception into
AI provider prompts, perform background observation, create durable memory, change tool
visibility, add execution authority, or create Phoenix policy/grants. The legacy local
approval bridge remains unchanged.


## M112 - Bounded LYRA Perception Prompt Exposure v1

M112 exposes a bounded snapshot of the existing M111 perception context to the AI provider
at the start of a new tool-loop request. The provider-facing envelope contains only the
M111 summary fields and explicitly labels them as untrusted observed data, not instructions,
authorization, current user intent, or proof that the user's higher-level goal succeeded.

The renderer considers at most eight recent observations, truncates error codes for prompt
use, and enforces a 4096-character bound on the perception block. When no observations are
available, the original provider text is preserved unchanged. Action arguments and raw
`ActionResult.evidence` remain absent from the perception prompt.

The original user request remains the sole input to local request-scoped gates such as the
`open_application` visibility check. Perception text may inform model reasoning, but it
cannot expand the locally exposed tool set, bypass risk confirmation, authorize an action,
or change The Hands validation. Results produced inside the current loop continue through
the existing structured tool-result continuation path; M112 does not recursively rebuild
the perception envelope between steps.

M112 adds no persistence, background observation, new tool, Phoenix policy/grant, execution
authority, supervisor, OCR, or general UI Automation framework. Legacy direct planner
actions remain outside perception capture just as in M111.


## M113 - Bounded LYRA Personality Context v1

M113 introduces a fixed-schema, process-local personality context for LYRA. The context
contains one immutable current snapshot with three finite presentation axes: tone,
verbosity, and formality. LYRA identity and locale are fixed metadata rather than arbitrary
user-provided strings.

The v1 deliberately accepts enum values only and stores no free-form personality prompt,
instruction, goal, policy, approval, authority, or tool directive. Updating one style axis
preserves the others, reset restores the defaults, and snapshots are immutable. The
assistant host owns one context for its process lifetime; there is no history buffer and no
durable personality store.

M113 does not yet expose personality state to the AI provider, add UI controls for changing
it, infer personality from conversation, persist preferences, alter memory, change tool
visibility, authorize actions, bypass local confirmation, or create Phoenix policy/grants.
The Hands execution and perception boundaries remain unchanged.


## M114 - Bounded LYRA Personality Prompt Exposure v1

M114 exposes the current M113 finite personality snapshot to the provider at the start of
one tool-loop request. The presentation-only envelope contains exactly fixed LYRA identity,
locale, and enum-backed tone, verbosity and formality values. Its JSON is deterministic,
contains no arbitrary prompt/instruction fields, and is bounded to 512 characters.

The assistant host passes its process-local personality context to the tool loop. The
provider sees the most recent snapshot at request entry. The existing M112 perception
prompt remains separately bounded and marked as untrusted observed data; both envelopes
are composed before the provider call without changing the original request used by local
tool-visibility and confirmation gates. No personality context means the old provider text
is preserved byte for byte. Provider continuation after local actions remains structured.

M114 applies only to the normal tool-loop AI entry point, not legacy direct planner
replies or external AI-provider system instructions. It does not add UI controls, durable
preferences, inference, tools, grants, approval overrides, Phoenix authority, background
monitoring, or evidence of completion of the user's higher-level goal.


## M115 - Bounded LYRA Personality Host Controls v1

M115 adds three finite desktop host selectors and one reset control for the existing
M113 personality state. Each selector uses enum-backed values only; invalid UI
payloads are rejected and the controls are restored to the last valid snapshot.

The controls update the same process-local context already consumed by M114 at
provider request entry. They are disabled during active host work. Reset restores
the M113 defaults. Neither the controls nor the selected labels become instructions,
policies, authorization, new tools or verified task-completion evidence.

M115 adds no persistence, external voice calls, new memory behavior, new execution
primitives, autonomous monitoring, free-form instructions, Phoenix grants or policy,
or alterations to local request-scoped gates and confirmation. Existing UI and
The Hands tool-loop flows remain in place.


## M116 - Bounded LYRA Conversation History Exposure v1

M116 adds a bounded, process-local provider-history projection over the existing
`SessionContext` conversation history. The existing visible/session snapshot remains
unchanged. The new `provider_snapshot()` emits only a contiguous suffix of complete
`ConversationTurn` objects, ordered oldest to newest, with three independent caps:
12 turns, 1024 characters per turn, and 4096 characters of turn text in total.

The history projection scans newest first and stops at the first turn that cannot
fit either character budget. It never truncates a turn, silently skips a middle
turn to reintroduce older context, persists history, summarizes with a model, or
changes the current request text. The desktop host uses this projection only when
passing prior history into the normal provider tool-loop entry point.

Historical conversation text remains untrusted contextual data, not current user
intent, executable instruction, policy, grant, approval, or proof of higher-level
goal completion. Request-scoped `open_application` visibility and local confirmation
continue to use the raw current request and existing local gates.

M116 does not introduce memory persistence, provider-interface changes, automatic
conversation summaries, background inference, a supervisor, Phoenix authorization,
new execution primitives or expanded tool visibility. Direct planner routes retain
their existing behavior. A separate Windows dogfood is required before publication.


## M117 - Explicit LYRA Session Reset Host Control v1

M117 adds one user-initiated "Nova conversa" action in the desktop host. The control
requests explicit confirmation, with No as the default, before clearing only the
current process-local visible chat transcript, draft input, M116 SessionContext and
M111 PerceptionContext observations. The UI returns to an idle workflow label and
shows one non-persisted acknowledgement after the clear. It does not infer a reset
from a model reply or an old conversation turn.

The reset button is disabled while the host is busy, and its handler independently
rejects programmatic attempts while disabled. The existing context and perception
objects stay attached to the host/tool loop; their process-local contents are cleared
in place. Previous context cannot reappear in the next provider-history projection or
perception prompt. A rejected confirmation changes nothing.

Personality style and its provider prompt remain unchanged. SQLite saved memory and
any other persistent storage are not deleted, and this feature is not a secure data
erasure facility. The reset neither cancels nor authorizes a task; it is unavailable
during active work. There is no Phoenix policy/grant, persistence migration, new
execution capability, background inference, tool-visibility expansion, or external AI
request in the reset operation.


## M118 - Bounded LYRA Context Visibility Host v1

M118 adds a passive host label showing bounded process-local metadata for the next
provider request: the count and total characters of the existing M116 contiguous
provider-history suffix, and the count of existing M111 perception observations.
It uses the current M116 projection and M111 snapshot directly. The label contains
no raw conversation text, action arguments, evidence mappings, provider replies,
or instructions, and makes no assertion that a higher-level task was completed.

The label updates after new session turns, normal task completion (including
perception captured by the tool loop), and a confirmed M117 session reset. It
never changes the snapshots it observes. The displayed history describes the
next eligible provider request, not an already in-flight provider request.

M118 creates no new authority, tools, approval policy, local execution primitive,
persistent storage, telemetry, periodic polling, background inference, or changes
to Phoenix. Existing request-scoped gates still use current raw user intent.
