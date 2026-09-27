# THE OS

Assistant-first Windows environment centered on **LYRA**.

## Current vertical slices

The repository currently proves seven boundaries:

1. **Verified Windows action** — deterministic intent -> `ActionRegistry` -> Windows adapter -> process verification.
2. **Persistent LYRA memory** — explicit remember/recall intents backed by local SQLite.
3. **Provider-neutral AI conversation** — unmatched conversation can fall through to a configured AI provider.
4. **Bounded session context + planner routing** — visible user/LYRA turns are kept in memory for the current process.
5. **AI tool planning with local authority** — the model may propose only tools advertised by THE OS; THE OS validates the proposal, converts it to a registered `ActionRequest`, executes locally, and reports verified results.
6. **Verified multi-step tool loop** — after each successful local action, THE OS returns the verified result to the model so it can continue the same request with the next required action. The loop is capped at four local actions and stops immediately on failure.
7. **Local risk policy + confirmation gate** — action risk is resolved by THE OS, not by the model. `READ_ONLY` and `NORMAL` actions may proceed automatically; `CONFIRM`, `DESTRUCTIVE`, and `PRIVILEGED` actions pause before side effects and require explicit user approval.

The model never receives arbitrary shell execution. Tool calls are proposals only. The local `ToolCatalog` is an allowlist and `ActionRegistry` remains the execution authority.

Risk classification is also local authority. In the first M7 policy, launching shells or administrative system tools through `open_application` is classified as `CONFIRM`, while ordinary applications such as Notepad remain `NORMAL`.

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
