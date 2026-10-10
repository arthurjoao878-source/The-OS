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
26. M119: Bounded LYRA Transcript Find Host v1, explicit literal navigation of
    the visible conversation without provider calls or new authority.
27. M120: Bounded LYRA Draft Recall Host v1, reusing recent local user
    submissions in the unsent composer without provider calls or new authority.
28. M121: Explicit LYRA Transcript Follow Host v1, letting the user choose
    whether new text auto-scrolls the visible chat without new authority.
29. M122: Bounded LYRA Chat Font Size Host v1, finite explicit chat-only
    presentation choices with the original system font as the default.
30. M123: Bounded LYRA Composer Length Host v1, explicit 4096-character text
    entry ceiling and passive length-only counter without changing authority.
31. M124: Explicit LYRA Transcript Viewport Navigation Host v1, user-initiated
    jump to the beginning or end of the visible chat without new authority.
32. M125: Bounded LYRA Transcript Find Match Count Host v1, finite literal
    occurrence counts displayed only after an explicit transcript find action.
33. M126: Bounded LYRA Transcript Find Match Position Host v1, showing
    the selected result rank within the already bounded literal find operation.
34. M127: Explicit LYRA Transcript Case-Sensitive Find Host v1, finite
    user-selected literal matching mode without any new authority.
35. M128: Explicit LYRA Transcript Whole-Word Find Host v1, opt-in
    complete-word matching without additional authority.
36. M129: Explicit LYRA Transcript Keyboard Find Shortcuts Host v1,
    bounded Ctrl+F/F3/Shift+F3 search navigation without new authority.
37. M130: Explicit LYRA Transcript Clear Find Host v1, clearing only the
    search query and labels on user request without new authority.
38. M131: LYRA Escape Search Focus Shortcut Host v1, explicit Escape only
    while the query has focus to restore the composer without new authority.
39. M132: LYRA Enter Search Navigation Shortcuts Host v1, widget-scoped
    Return/Shift+Return navigation through existing find handlers.
40. M133: Explicit LYRA Composer Focus Shortcut Host v1, window-scoped Ctrl+M
    to focus the unsent-message composer without sending or new authority.
41. M134: Explicit LYRA Transcript Focus Shortcut Host v1, window-scoped
    Ctrl+Shift+M to focus the read-only transcript without new authority.
42. M135: Explicit LYRA Transcript Follow Toggle Shortcut Host v1, window-scoped
    Ctrl+Shift+A to toggle the existing follow-new-messages control.
43. M136: Explicit LYRA Chat Font Size Cycle Shortcut Host v1, window-scoped
    Ctrl+Shift+T to cycle the four existing chat-only font sizes.
44. M137: Explicit LYRA Whole-Word Find Toggle Shortcut Host v1, window-scoped
    Ctrl+Shift+W to toggle the existing literal whole-word search mode.
45. M138: Explicit LYRA Case-Sensitive Find Toggle Shortcut Host v1, window-scoped
    Ctrl+Shift+C to toggle existing literal case-sensitive search mode.
46. M139: Explicit LYRA Clear Find Shortcut Host v1, window-scoped
    Ctrl+Shift+L to clear only the current transcript search query and labels.
47. M140: Explicit LYRA Jump End Shortcut Host v1, window-scoped
    Ctrl+Shift+J to jump to transcript end, even while tasks are busy.
48. M141: Explicit LYRA Jump Start Shortcut Host v1, window-scoped
    Ctrl+Shift+K to jump to transcript start, even while tasks are busy.
49. M142: Bounded LYRA Task Timeline Host v1, explicit read-only panel
    presenting up to 12 recent M102/M103 summary events for the current task.
50. M143: Bounded LYRA Direct Action Timeline Host v1, presenting only
    approved direct-action lifecycle IDs and evidence-qualified outcomes.
51. M144: Bounded LYRA Failure and Cancellation Visibility Host v1, presenting
    cancel requests as nonterminal and processing failures as fixed safe labels.
52. M145: Bounded LYRA Task Summary Host v1, showing only rolling event count
    and a fixed, evidence-qualified classification of the latest presentation state.
53. M146: Bounded LYRA Interruption Timeline Filter Host v1, explicitly filtering
    only recognized failure and cancellation presentations within 12 events.
54. M147: Explicit LYRA Task Timeline Toggle Shortcut Host v1, window-scoped
    Ctrl+Shift+E for the existing read-only task history panel, with no dispatch.
55. M148: Explicit LYRA Interruption Filter Shortcut Host v1, window-scoped
    Ctrl+Shift+I to toggle the existing bounded read-only interruption filter.
56. M149: Bounded LYRA Interruption Count Host v1, read-only count of
    recognized interruption presentations in the retained 12 recent events,
    including requested cancellations, not a count of verified effects.
57. M150: Bounded LYRA Interruption Breakdown Host v1, read-only counts
    separating pending cancellation requests, confirmed cancellations and
    failures within the same retained 12 classified presentation events.
58. M151: Bounded LYRA Interruption Category Filter Host v1, an explicit
    finite read-only selector that narrows the existing 12-event interruption
    timeline to pending requests, confirmed cancellations or failures.
59. M152: Explicit LYRA Interruption Category Cycle Shortcut Host v1, a
    window-scoped Ctrl+Shift+Y shortcut that cycles the existing safe selector.
60. Then continue user-facing LYRA capabilities, voice, and composed workflows as
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


## M119 - Bounded LYRA Transcript Find Host v1

M119 introduces an explicit, process-local Find bar in the desktop host for the
currently visible chat transcript. The user can search literal text forward or
backward with a bounded query (at most 120 characters) and wrapping navigation.
Search is case-insensitive, read-only, and never invokes the AI provider or
reads SQLite, previous sessions, tools, process observations, or raw evidence.

The host declines searching a visible transcript larger than 65536 characters.
Only neutral status strings (ready, selected, no result, above limit) are shown;
no matched content, query text or sensitive evidence is copied to status labels.
Find widgets are disabled while host work is active, and the handler independently
rejects direct invocation while disabled. Confirmed M117 session reset clears
the search query and status with the visible chat.

M119 does not change M116 history projection, M118 context indicators, provider
prompts, persistent memory, personality, tool visibility, local confirmations,
execution semantics, or Phoenix authority. It adds no filesystem export, data
retention, background inference, telemetry, or autonomous navigation.


## M120 - Bounded LYRA Draft Recall Host v1

M120 adds two explicit desktop composer controls to navigate previously submitted
user turns in the current process-local session. Navigation is read-only over the
existing M116 SessionContext snapshot, and only injects a chosen, complete string
into the unsent QLineEdit draft. Nothing is sent to the provider or routed to
The Hands until the user explicitly submits the composer using the existing path.

The projection retains at most eight most recent user submissions, at most 1024
characters each. Oversized or multiline turns are omitted rather than truncated.
Assistant replies, perception, persistent memory and earlier process sessions are
not sources. The first backward navigation saves the user's unsent draft, and
forward navigation past the newest submission restores it. Editing the composer
manually, submitting, or a confirmed M117 reset discards navigation state.
Each host instance owns its own temporary navigation state.

Navigation is disabled during busy host work, and handlers reject direct attempts
while disabled. The original request-scoped tool visibility and confirmation
gates still apply if the user explicitly resubmits a recalled request. This
feature neither adds new tools, voice, persistence, background inference nor
Phoenix grants. It does not change model prompts or the authority boundary.


## M121 - Explicit LYRA Transcript Follow Host v1

M121 adds a checked-by-default "Acompanhar novas mensagens" option adjacent to the
read-only chat transcript. When enabled, newly appended user and LYRA messages
scroll to the end; when disabled, append operations preserve the user's current
vertical scroll position. Enabling it again scrolls to the latest text. This
choice remains operable during a busy host task, including tool-loop progress.

Only the viewport is affected. The option never reads or copies raw chat content,
changes the original current user request, invokes the provider, alters SessionContext
or PerceptionContext, reads persistent memory, creates tools, expands confirmation
policy, or introduces Phoenix authority. It has no storage or external effects.
A confirmed M117 session reset returns follow to its on-by-default state; a
denied reset leaves it unchanged. Each host instance has isolated toggle state.
Existing M119 find, M120 draft recall, and normal send and approval paths remain
unchanged. A separate Windows Qt runtime dogfood remains required before delivery.


## M122 - Bounded LYRA Chat Font Size Host v1

M122 introduces one finite explicit desktop option controlling only the font of the
existing read-only LYRA chat. The user can select System (unchanged original host
font), Small (10 pt), Normal (12 pt), or Large (16 pt). System is the default and
restores the original QFont, including non-size font properties. Unsupported combo
data fail closed without applying an unexpected font size.

Font-size changes are synchronous, process-local and available while the host is
busy. They do not change transcript text, scroll-follow preference, search or
composer widgets, previously submitted requests, provider prompt, local action
intent, task execution, or available tools. This control does not read or mutate
SessionContext, PerceptionContext, personality, SQLite memory, or Phoenix authority,
and never calls an AI provider. There is no persistent preference or telemetry.

A confirmed M117 New Conversation resets this setting to System; a rejected reset
preserves the chosen size. Independent host windows keep separate settings. The
M119 find and M120 draft recall controls remain available and unchanged. A distinct
real Windows Qt-host dogfood is needed before publishing the local commit.


## M123 - Bounded LYRA Composer Length Host v1

M123 makes the existing LYRA QLineEdit input limit explicit at 4096 characters and
shows a passive, length-only counter beside Send. The counter reflects the
currently displayed, unsent text, including restored drafts, and never displays
its contents. QLineEdit applies its normal truncation to overlong pasted input;
users are informed of the ceiling in the UI. The host also independently rejects
overlong or disabled direct submissions instead of invoking the planner.

The change introduces no new submissions, hidden provider requests, history
exposure, memory persistence, filesystem exports, mic access, or Phoenix
authority. It does not change existing action confirmation or tool visibility.
It preserves the M120 bounded draft recall, M119 find, M121 follow, M122 font,
and the existing normal explicit Send route. Busy work disables the composer,
and a confirmed M117 session reset clears the draft and resets its counter; a
rejected reset preserves both. Each host window has its own counter.

Separate full pytest/Ruff and real Windows Qt dogfood gates are required before
remote publication.


## M124 - Explicit LYRA Transcript Viewport Navigation Host v1

M124 adds two explicit controls, Inicio and Final, beside the current chat follow
checkbox. A click moves only the existing read-only transcript's vertical Qt
scrollbar to its minimum or maximum. The controls do not read transcript content,
change find selections, modify message text, switch follow on or off, or edit an
unsent request. Existing M121 follow semantics remain unchanged: if follow is
on, later append operations scroll to the end; if it is off, later appends
preserve the position, even after an explicit navigation click.

Both controls remain available during a busy task so the user can read earlier
or newer progress. Each window owns its own viewport state. A confirmed M117
reset clears the visible transcript as before, after which navigation remains
available; a rejected reset changes nothing. M119 find, M120 draft recall,
M122 font size, and M123 composer length remain unchanged.

This is synchronous process-local presentation only: no provider request,
tool invocation, clipboard access, filesystem write, persistence, background
inference, microphone, approval bypass, or Phoenix authority. Separate full
pytest/Ruff and real Windows Qt dogfood gates are required before publication.


## M125 - Bounded LYRA Transcript Find Match Count Host v1

M125 extends the existing M119 user-initiated literal transcript search with a
passive number-only count label. Counts are computed only when the user activates
Next or Previous on a valid query, using the Qt document's case-insensitive
literal find semantics. At most 257 matches are examined: 0 through 256 are
reported exactly and additional matches are shown as "256+". The existing
120-character query limit and 65536-character conversation limit apply before
counting. Empty queries reset the label to neutral; rejected oversized inputs
show an unavailable count. Editing the query resets the label without scanning.

The scan uses a separate QTextCursor and never changes the visible selection,
search direction, transcript text, follow preference, draft, session context,
perception context, personality, or memory. The existing busy-task search
disablement remains in force and direct handler invocation is rejected while
busy. A rejected new-conversation reset preserves the label and query; an
accepted reset clears both. Different host instances remain isolated.

This is process-local presentation only: no provider request, tool invocation,
clipboard, persistence, filesystem effects, microphone, approval bypass, or
Phoenix authority. Full pytest/Ruff and a separate real Windows Qt dogfood
remain required before publication.


## M126 - Bounded LYRA Transcript Find Match Position Host v1

M126 extends the M125 finite, explicit transcript find count by presenting which
literal match is currently selected. After an explicit Next or Previous request,
its read-only position label shows rank and total, such as "Posição: 2 de 4".
No scanning occurs while the user types. The same Qt document cursor, case-
insensitive literal search, 120-character query ceiling, 65536-character visible
transcript ceiling, and at-most-257 match traversal are retained. For a selected
result beyond the exact first 256, the position is reported as ">256" against
"256+" total, never as an invented precise rank. No matches show a neutral rank;
rejected oversized queries or transcripts show an unavailable rank.

The rank is computed using a separate QTextCursor after the normal find has
selected a result, so it never overwrites the selected text or scroll behavior.
The M125 count and M119 search status retain their existing semantics. Typing a
new query resets both labels without scanning. Busy direct-handler guards still
reject search; denied session reset preserves both labels and confirmed reset
clears them. Separate host windows have isolated status.

This change affects process-local presentation only: no new provider requests,
tools, authority, memory, persistence, filesystem, clipboard, microphone,
background inference or bypass of confirmations. Full pytest/Ruff and Windows
real Qt dogfood are mandatory before publishing the local commit.


## M127 - Explicit LYRA Transcript Case-Sensitive Find Host v1

M127 adds one explicit host-only checkbox below transcript search to toggle
case-sensitive literal matching. It starts unchecked, preserving the prior
case-insensitive M119/M125/M126 behavior. When checked, Next and Previous use
QTextDocument.FindCaseSensitively combined with optional FindBackward; the bounded
M125 count and M126 selected rank use exactly the same case-sensitivity flags.
All searches stay literal (not regex). Mode changes clear count/rank and search
status without starting a scan, changing the text query or visible selection,
or calling the provider. The next explicit Next/Previous request performs the
search using the chosen mode.

The 120-character query ceiling, 65536-character transcript ceiling and
257-match scan bound remain unchanged. Busy tasks disable this checkbox alongside
search, and the existing direct-handler guard still rejects search while busy.
A rejected new-conversation reset preserves the mode and results; an accepted
reset restores the insensitive default and clears search state. Different host
windows have independent settings. The change does not alter transcript content,
follow/navigation, draft, provider history, memory, personality, tool catalog,
authority gates, execution control, persistence or filesystem state. It performs
no background scanning, AI provider requests, microphone access, clipboard
access or approval bypass. Full pytest/Ruff and separate real Windows Qt
dogfood are required before remote publication.


## M128 - Explicit LYRA Transcript Whole-Word Find Host v1

M128 adds one opt-in whole-word checkbox to the existing literal transcript
search. It is unchecked by default, retaining the M119 substring semantics.
When enabled, Next/Previous use Qt QTextDocument.FindWholeWords, combined with
M127 FindCaseSensitively when separately checked and FindBackward for Previous.
The bounded M125 occurrence count and M126 selected rank use exactly the same
matching flags. This is the Qt definition of whole-word boundaries, not a
regular expression or arbitrary linguistic tokenization.

Either search mode checkbox invalidates count, rank and status without scanning,
changing the query, or replacing the active text selection. A scan runs only
after explicit Next/Previous. The query remains limited to 120 characters,
the transcript to 65536 characters, and the scan to at most 257 matches;
counts and ranks past 256 remain imprecise by design. Busy work disables
both search options and the existing direct-handler guard remains in force.
Denied new-conversation reset preserves these settings; a confirmed reset
returns both to unchecked. Settings are per-window, process-local and not
persisted.

The feature does not affect transcript contents, scroll follow, conversation
context, perception, personality, unsent draft, memory, tools, approval gates,
execution, provider requests or Phoenix authority. It adds no clipboard,
filesystem effects, network activity, microphone use or background inference.
Full pytest/Ruff and separate real Windows Qt dogfood are required before any
remote publication of the local commit.


## M129 - Explicit LYRA Transcript Keyboard Find Shortcuts Host v1

M129 adds three explicit, process-local shortcuts to the existing read-only
transcript search: Ctrl+F focuses the existing query field, F3 uses the same
Next handler, and Shift+F3 uses the same Previous handler. They are QShortcut
objects with WindowShortcut context and no independent search implementation.
No key submits a chat message, invokes a provider or action, changes permissions,
or reads persistent memory. All navigation uses the current 120-character query,
65536-character visible transcript and existing at-most-257 match traversal.
M127 case-sensitivity and M128 whole-word matching remain effective, including
the M125 count and M126 rank. Empty query and no-match behavior are unchanged.

While the host is busy, all three shortcuts and the search controls are disabled;
directly invoked handlers also reject busy operation. Confirmed new conversation
clears search as before; rejected reset keeps the search untouched. Each window
has independent shortcut objects and query state, without global hotkeys or
persistent preferences. The feature has no filesystem, network, clipboard,
microphone, background inference or Phoenix authority. Separate full pytest
and Ruff plus a real Windows Qt-host dogfood gate are required before any push.


## M130 - Explicit LYRA Transcript Clear Find Host v1

M130 introduces one explicitly clicked "Limpar busca" button next to the
existing LYRA transcript query. It clears only the local find query and resets
the previous M119 find status, M125 bounded occurrence count, M126 selected
rank, and last-query navigation marker to neutral. It does not invoke a find,
scan the document, deselect the current text, move the viewport, alter the
follow preference, change the unsent composer draft, or submit a request.
Clicking when the query is already empty still restores neutral labels.

M127 case sensitivity and M128 whole-word settings are preserved so the user
can clear and reenter terms without losing the search modes. M129 Ctrl+F,
F3 and Shift+F3 shortcuts remain unchanged. The button and the input are
disabled during a busy task, with a direct-handler guard against bypass.
Denied new-conversation reset does not clear the search; accepted reset keeps
the button available and clears the query through the existing path. Each
host window keeps its own query, status and search settings.

This is process-local presentation only and adds no provider calls, tools,
clipboard access, file/network effects, persistent memory access, new task
authority, background inference or approval bypass. Existing 120-character
query and 65536-character visible transcript ceilings, 256+ result bound,
provider history caps, and Phoenix authority are unchanged. Full pytest,
Ruff and separate real Windows Qt dogfood must pass before publication.


## M131 - LYRA Escape Search Focus Shortcut Host v1

M131 adds a widget-scoped Escape shortcut to the existing LYRA transcript
find field. The QShortcut is parented to the find QLineEdit and explicitly
uses WidgetShortcut scope, so Escape only redirects focus while that exact
field has focus. The direct handler checks both the find and composer input
are enabled and that the find field has focus; busy tasks disable the shortcut
and both inputs. Escape moves focus to the unsent-message composer only. It
does not remove or modify the query, labels, selection, scroll position,
follow state, case sensitivity, whole-word mode, search bounds or keyboard
find shortcuts. The existing explicit M130 clear button remains the sole
find-clear command and still resets the query and labels.

The shortcut is process-local, per-window, and not global or persisted.
Neither ordinary Escape in the composer nor Escape inside a modal dialog
initiates a find or alters conversation state. Denied and accepted session
reset continue their previous behaviors; the shortcut survives reset. No
AI provider calls, tools, memory or personality effects, clipboard access,
filesystem or network side effects, actions or approval bypass are added.
Full pytest/Ruff and real Windows Qt dogfood remain required before push.


## M132 - LYRA Enter Search Navigation Shortcuts Host v1

M132 adds two explicit widget-scoped QShortcuts to the existing transcript
find QLineEdit: Return navigates to the next match and Shift+Return navigates
to the previous match. Both are parented to the query input, use WidgetShortcut
context and delegate directly to the existing M125-M129 Next and Previous
handlers, so the same literal matching, case/whole-word modes, count and
selection rank, wrapping and 120/65536-character bounds remain authoritative.
There is no second search implementation, automatic search-on-keystroke,
background scanning or message submission. Pressing Return in the composer
has no new handler from this feature; its established behavior is unchanged.

When the host is busy both shortcuts and the query input are disabled, while
the shared find handlers retain their direct busy guards. These objects are
window-local, process-local and not persisted. M131 Escape returns focus to
the composer without clearing the query; M130 Clear Find remains explicit.
Denied and accepted new-conversation reset preserve the shortcut objects,
while a confirmed reset clears query and indicators as before. No new provider
request, tool, memory/personality mutation, permission, clipboard, filesystem,
network or Phoenix authority is introduced. Full pytest/Ruff plus independent
real Windows Qt offscreen dogfood are required before remote publication.


### M132 numeric Enter recovery

M132 real Windows Qt dogfood TOS475 exposed the distinction between Qt Key_Return
and Key_Enter: a numeric-keypad Enter event was not mapped by the original
Return-only shortcuts. The local M132 commit now has two additional shortcuts,
Key_Enter and Shift+Enter, parented to the query QLineEdit and restricted to
WidgetShortcut context. They reuse the existing next/previous handlers and
are disabled during busy tasks. This is a strictly local keyboard behavior
recovery: no provider call, message submission, new task execution,
persistent-memory access, authority or approval change is added. M132 remains
unpublished pending full pytest/Ruff and independent Windows real Qt dogfood.


## M133 - LYRA Composer Focus Shortcut Host v1

M133 adds an explicit Ctrl+M shortcut to focus the existing unsent-message
composer from the transcript or find widgets. The QShortcut is owned by the
LYRA MainWindow, with WindowShortcut context (never application-global).
Its handler only calls input.setFocus when the composer is enabled; busy task
state disables the shortcut and direct invocation returns without effect.
Ctrl+M never calls submit or the provider, sends any message, starts a task,
changes a draft, query, find selection, match rank, viewport, follow setting,
conversation history, perception, persistent memory, or personality.
Session reset retains the shortcut, while existing confirmation and guards
remain unchanged. No new clipboard, filesystem, networking, action authority,
or Phoenix policy is introduced. Full pytest and Ruff plus independent real
Windows Qt keyboard dogfood are required before remote publication.


## M134 - LYRA Transcript Focus Shortcut Host v1

M134 adds an explicit window-scoped Ctrl+Shift+M shortcut to focus the
existing read-only conversation transcript from the composer or find field.
It does not select, edit, copy, send or export transcript content, nor does
it change scroll, following, query, match count/rank, draft, context,
perception, personality or persistent memory. The shortcut has no effects
outside its LYRA window. Busy task state disables activation and direct
invocation fails closed. The M133 Ctrl+M composer shortcut, M129 Ctrl+F find
shortcut, Escape and Enter find navigation remain separate. No new tools,
provider calls, approvals, filesystem/network/clipboard permissions or
Phoenix authority are introduced. Full pytest/Ruff and independent real
Windows Qt key-event dogfood are required before publication.


## M135 - LYRA Transcript Follow Toggle Shortcut Host v1

M135 adds a window-scoped Ctrl+Shift+A shortcut that explicitly toggles
the existing process-local Acompanhar novas mensagens checkbox through its
normal checked state and previously implemented Qt signal handler. The
default remains on. Toggling off preserves the reader position on new
messages; toggling on retains the existing scroll-to-end behavior. The
shortcut does not change text, search query/count/rank, draft, context,
perception, personality, memory or any Phoenix authority. Busy task state
disables the shortcut and directly calling its handler fails closed. The
checkbox itself remains independently usable under its existing policy.
Window-local isolation, old keyboard shortcuts, user confirmation gates,
and both reset outcomes must remain unchanged. No provider calls, actions,
filesystem/network access or new capability is added. Independent real
Windows Qt key-event dogfood, full pytest and Ruff are required before push.


## M136 - LYRA Chat Font Size Cycle Shortcut Host v1

M136 adds a window-scoped Ctrl+Shift+T shortcut to cycle the existing
four chat-only QComboBox font selections in order: Sistema, Pequeno (10),
Normal (12), Grande (16), then Sistema. The QComboBox remains the only
state source, and its existing currentIndexChanged handler applies the font.
The shortcut fails closed if the combo model is not the expected four-option
finite model or if the shortcut or combo is disabled. Busy tasks disable the
shortcut without expanding the previous combo policy. This purely local
presentation change does not edit messages, query, match counters, drafts,
conversation history, perception, personality or persistent memory. It does
not call a provider, run actions, add permissions or change Phoenix authority.
Manual size choices and reset-to-Sistema behavior remain unchanged.
Real Windows Qt keyboard dogfood, the full pytest suite and Ruff must pass
before separate publication of the exact existing local commit.


## M137 - LYRA Whole-Word Find Toggle Shortcut Host v1

M137 adds a window-scoped Ctrl+Shift+W shortcut that toggles only the existing
whole-word literal search QCheckBox. The current checked-state and existing
toggled signal remain the source of truth. As with manually clicking this
checkbox, the query remains unchanged, current count and rank labels are
invalidated without running a search, and the transcript's selected text
and reading position are not changed by the shortcut handler. The new
shortcut requires the search input, whole-word checkbox and shortcut itself
to be enabled, and is disabled while work is busy. Case sensitivity is
independent. The find limit remains 120 characters for the query, 65536
for the transcript and 256 for counted matches. This feature has no new
Phoenix authority, task execution, provider calls, memory writes, or
conversation mutations. A separate real Windows Qt keyboard dogfood and a
separate exact existing-commit finalizer are required before closure.


## M138 - LYRA Case-Sensitive Find Toggle Shortcut Host v1

M138 adds window-scoped Ctrl+Shift+C to toggle only the existing literal
case-sensitive search QCheckBox. The checkbox's toggled signal remains the
source of truth. Toggling invalidates match-count and match-rank labels
without scanning. The query, draft, transcript, selection, focus and follow
state are preserved. Whole-word mode is independent. The shortcut requires
the search input, case-sensitive checkbox and shortcut to be enabled, and
is disabled while tasks are busy. Existing 120-character search, 65536
transcript and 256-result bounds remain unchanged. No new Phoenix authority,
provider calls, task execution, memory writes or conversation mutation.
Separate real Windows Qt dogfood and exact existing-commit finalization
are required before closure.


## M139 - LYRA Clear Find Shortcut Host v1

M139 adds window-scoped Ctrl+Shift+L to invoke only the existing
clear-search handler. The shortcut clears the query and match count/rank
indicators without scanning the transcript, changing whole-word or case
mode, removing transcript text, changing selection, or changing the draft.
It is disabled while tasks are busy; its direct handler is fail-closed
when the search input, clear button or shortcut are disabled. Search
bounds remain intact and no new Phoenix authority, provider calls, task
execution, memory writes or conversation mutation are introduced.
Separate real Windows Qt dogfood and exact existing-commit finalization
are required before closure.


## M140 - LYRA Jump End Shortcut Host v1

M140 introduces a window-scoped Ctrl+Shift+J shortcut reusing the
existing passive chat jump-to-end action. Navigation remains available
while tasks are busy, as with the existing navigation buttons. It never
changes the follow-new-messages mode, search state, draft, conversation
text, selection, personality, persistent memory, task context, or provider.
Its direct handler checks the existing transcript widget, end button, and
shortcut enabled states before navigating. No new Phoenix authority or
execution effects are introduced. Separate real Windows Qt dogfood and
exact commit publication are required to close M140.


## M141 - LYRA Jump Start Shortcut Host v1

M141 introduces a window-scoped Ctrl+Shift+K shortcut reusing the
existing passive chat jump-to-start action. Navigation remains available
while tasks are busy, as with the existing navigation buttons. It never
changes follow-new-messages, search state, draft, conversation content,
selection, personality, persistent memory, task context, or provider.
The direct handler checks the existing transcript widget, start button,
and shortcut enabled states before navigating. No new Phoenix authority
or execution effects are introduced. Separate real Windows Qt dogfood
and exact commit publication are required to close M141.

## M142 - Bounded LYRA Task Timeline Host v1

M142 exposes an opt-in, read-only, process-local timeline of up to 12
recent summarized workflow states already produced by M102/M103.
Only `HostWorkflowProgressView.text` is retained, bounded to 180
printable characters per entry. Adjacent duplicate states are omitted;
older states are discarded deterministically. This is a presentation
trace, not durable audit evidence or a verified effect ledger.
The panel is hidden by default, available during busy tasks, and cleared
when a new tool-loop task starts or an approved session reset occurs.
Denied reset preserves it. It never copies intent, raw action arguments,
provider prompts, file contents, or execution evidence. No persistent
write, external AI call, new tool, action, supervision, or Phoenix
authority is introduced. Separate Windows Qt dogfood and controlled
publication are required before M142 can be closed.

## M143 - Bounded LYRA Direct Action Timeline Host v1

M143 extends the closed M142 read-only, process-local, 12-entry timeline
for direct actions that have passed existing local authority gates.
The direct-action path shows a fixed bounded action identifier at worker
submission, then a result status associated only with its exact request ID.
ActionResult.success alone never asserts that an effect was dispatched or a
postcondition verified. Only explicit effect_dispatched and
postcondition_verified evidence fields permit those respective labels.
Failure is always reported as a failure, even if fields conflict.
No action arguments, result.message, raw evidence, secret strings,
file contents, or provider prompts are retained in the panel. Denied
actions never enter it; starting a new task or approved session reset
clears prior entries. This adds no new registry actions, execution
permissions, confirmation bypass, model call, provider access, memory
mutation or Phoenix authority. Run real Windows Qt dogfood and gated
remote publication separately before closing M143.


## M151 - Bounded LYRA Interruption Category Filter Host v1

M151 extends M146's opt-in read-only interruption-only timeline with a
four-choice finite Qt category selector: Todas, Pendentes, Canceladas, Falhas.
The default Todas retains all M146 interruption entries and original event
numbers. The three narrowed views use M150's existing recognized and bounded
classifications only; invalid or missing selector data yields the safe empty
message rather than falling back to an unfiltered private event list.

The selection has no effect until Somente interrupções is checked. Toggling
Ctrl+Shift+I off restores the complete M142 timeline; on applies the saved
category. Ctrl+Shift+E keeps its previous panel behavior. The category and
checkbox remain process-local and per-window, and may be used during busy
tasks to inspect only already presented events. Neither changes the underlying
12-event buffer, counts, summaries, original order, or raw evidence boundaries.
A denied reset preserves the view; an approved reset clears task events but
preserves the chosen filter. A new task clears old events while retaining the
local view. There are no new tools, actions, provider calls, permission grants,
automatic task execution, persistent memory writes, or Phoenix policy changes.
Full pytest, Ruff and independent real Windows Qt dogfood must pass before an
exact-commit publication on main.


## M152 - Explicit LYRA Interruption Category Cycle Shortcut Host v1

M152 introduces the window-scoped Ctrl+Shift+Y shortcut to cycle only the
existing M151 interruption-category QComboBox: Todas, Pendentes, Canceladas,
Falhas, then wrap to Todas. It invokes QComboBox.setCurrentIndex so the existing
M151 currentIndexChanged refresh remains the sole presentation path; there is
no second filtering implementation. When Somente interrupções is unchecked,
changing the selector does not narrow the visible full task history. The
selection remains local and available during busy tasks because both the
M151 selector and M146 read-only timeline are already available then.

The direct handler fails closed when the shortcut or selector is disabled,
when the current index is invalid, or when the finite four-option text/data
model differs from the expected order. It does not repair a corrupted model,
infer a category, or fall back to revealing extra events. The existing safe
M151 category view handles invalid selector data. A denied reset retains
the selection; an approved reset clears events but retains the selection and
shortcut. Different LYRA windows have independent selector state.

M147 Ctrl+Shift+E and M148 Ctrl+Shift+I remain unchanged. The shortcut does not
submit conversation input, start tasks or actions, call an AI provider, mutate
conversation context, personality, unsent drafts or persistent memory, or
change The Hands execution or Phoenix authority. The same 12-event bound,
M149/M150 counts and evidence qualifications remain intact. Full pytest,
Ruff and a separate Windows Qt keyboard dogfood are required before an
exact-commit finalizer may publish M152.
