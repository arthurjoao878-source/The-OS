# THE OS

Assistant-first Windows environment centered on **LYRA**.

## Current vertical slices

The repository currently proves thirteen boundaries:

1. **Verified Windows action** — deterministic intent -> `ActionRegistry` -> Windows adapter -> process verification.
2. **Persistent LYRA memory** — explicit remember/recall intents backed by local SQLite.
3. **Provider-neutral AI conversation** — unmatched conversation can fall through to a configured AI provider.
4. **Bounded session context + planner routing** — visible user/LYRA turns are kept in memory for the current process.
5. **AI tool planning with local authority** — the model may propose only tools advertised by THE OS; THE OS validates the proposal, converts it to a registered `ActionRequest`, executes locally, and reports verified results.
6. **Verified multi-step tool loop** — after each successful local action, THE OS returns the verified result to the model so it can continue the same request with the next required action. The loop is capped at four local actions and stops immediately on failure.
7. **Local risk policy + confirmation gate** — action risk is resolved by THE OS, not by the model. `READ_ONLY` and `NORMAL` actions may proceed automatically; `CONFIRM`, `DESTRUCTIVE`, and `PRIVILEGED` actions pause before side effects and require explicit user approval.
8. **Cooperative task control** — conversational/tool tasks expose Pause, Resume, and Cancel controls. Pause blocks at safe execution checkpoints; Cancel prevents later local side effects and provider continuations after the next checkpoint.
9. **Bounded file/folder actions** — LYRA can inspect local path metadata, search names inside a user-specified root, and ask Windows to open an existing file or folder. Files with potentially executable/script suffixes are locally upgraded to `CONFIRM`.
10. **Controlled text-file reading** — LYRA can read at most 16 KiB from a local text file after explicit user confirmation. Binary-looking files are rejected; sensitive credential/key filenames are locally upgraded to `PRIVILEGED`.
11. **Previewed text-file mutation** — LYRA can create or fully replace a text file of at most 16 KiB only after THE OS prepares a local preview/diff and the user explicitly approves it. Existing files are `DESTRUCTIVE`; sensitive or executable/script-like paths are `PRIVILEGED`.
12. **Controlled path mutation** — LYRA can create one directory, move/rename a path without overwriting the destination, and send a path to the Windows Recycle Bin. Every mutation uses a local preview plus explicit approval; move/trash operations are `DESTRUCTIVE`, sensitive locations are `PRIVILEGED`, and protected Windows system paths cannot be moved or trashed.
13. **Bounded verified copy** — LYRA can copy a file or a directory tree while preserving the source. Copy is locally bounded to 256 entries and 64 MiB, refuses links/junctions and existing destinations, previews counts/size before approval, and verifies a content manifest before publishing the destination.

The model never receives arbitrary shell execution. Tool calls are proposals only. The local `ToolCatalog` is an allowlist and `ActionRegistry` remains the execution authority.

Risk classification is also local authority. Launching shells or administrative system tools through `open_application` is classified as `CONFIRM`, while ordinary applications such as Notepad remain `NORMAL`. For `open_path`, executable, script, shortcut, installer, and similar suffixes are also classified as `CONFIRM`.

Filesystem search is intentionally bounded: name search starts only from the root explicitly supplied to the tool, is depth-limited, and caps the number of matches. `inspect_path` returns metadata and a bounded directory listing.

`read_text_file` is deliberately not automatic even though it is read-only at the filesystem level. File contents are returned to the configured AI provider as tool data, so every read requires local confirmation before the file is touched. Known credential/key paths such as `.env`, private-key names, `.pem`, `.key`, `.p12`, and `.pfx` are classified as `PRIVILEGED`. The tool reads at most 16 KiB, rejects binary-looking data, and marks returned content as untrusted data so text inside a file is not authority to execute more actions.

`write_text_file` accepts only a complete replacement body of at most 16 KiB. Before approval, THE OS resolves the target locally, verifies that its parent exists, rejects directories, binary-looking existing files, and existing files larger than the bounded limit, then produces a unified diff for ordinary files. Sensitive paths use a redacted local preview so secrets are not printed into the LYRA chat. New ordinary files are `CONFIRM`, existing ordinary files are `DESTRUCTIVE`, and sensitive or executable/script-like paths are `PRIVILEGED`.

Approval carries a local execution guard containing the resolved path and hashes from the preview. If the target or proposed content changes between preview and execution, the write is blocked. Successful writes use a same-directory temporary file plus `os.replace`, then verify the resulting SHA-256. The tool never creates missing parent directories.

Copy is also bounded and verified. `copy_path` supports ordinary files and recursive directory trees up to 256 entries and 64 MiB total. Symbolic links and Windows junctions are rejected, existing destinations are never overwritten, and a content manifest is recalculated before and after the copy. The copied result is built at a temporary sibling path and published to the requested destination only after verification. Ordinary copies are `CONFIRM`; sensitive/executable or protected-system locations are `PRIVILEGED`.

Path mutation is intentionally bounded. `create_directory` creates only one level and never creates missing parent directories. `move_path` refuses existing destinations and blocks moving protected Windows system sources or moving a directory inside itself. `trash_path` uses the Windows Recycle Bin rather than permanent deletion, refuses protected system paths, and verifies that the original path disappeared after the shell operation. Mutation previews carry local path/signature guards so a changed source is blocked before execution.

`open_path` verifies that the target exists before handing it to the Windows shell. For generic files and folders, THE OS can verify the local target and that the shell-open request was submitted, but it does not claim that the associated GUI rendered successfully. Live visual acceptance remains the final check for that handoff.

Task cancellation is cooperative. THE OS does not forcibly kill a provider HTTP request or a local action that is already in progress. Instead, cancellation is checked before provider work, before local side effects, after each verified action, and before the next step. Pause follows the same safe checkpoints.

For the OpenAI Responses adapter, tool calls are deliberately serial (`parallel_tool_calls: false`). THE OS executes at most one model-proposed action at a time, verifies it locally, returns its `function_call_output`, and only then allows the model to propose the next step.

The Responses adapter remains stateless with `store: false`. It replays response output items and tool results locally for continuation and requests encrypted reasoning items when tools are enabled.

The session context is intentionally separate from persistent memory. Normal conversation is not automatically written to SQLite.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m theos
```

## AI configuration

Create a local `.env` file when a provider is ready to be used:

```text
THEOS_AI_PROVIDER=openai
THEOS_AI_MODEL=<model-id>
THEOS_AI_API_KEY=<secret>
THEOS_AI_BASE_URL=https://api.openai.com/v1
```

The real `.env` is ignored by Git. Without AI configuration, LYRA keeps actions and memory working and reports that conversational AI is not configured.

For conversational context, THE OS re-sends a bounded set of recent visible turns and requests `store: false` from the Responses API. Persistent memory remains a separate explicit local feature.

## Test

```powershell
python -m pytest -q
python -m ruff check .
```
