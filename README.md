# THE OS

Assistant-first Windows environment centered on **LYRA**.

## Current vertical slices

The repository currently proves five boundaries:

1. **Verified Windows action** — deterministic intent -> `ActionRegistry` -> Windows adapter -> process verification.
2. **Persistent LYRA memory** — explicit remember/recall intents backed by local SQLite.
3. **Provider-neutral AI conversation** — unmatched conversation can fall through to a configured AI provider.
4. **Bounded session context + planner routing** — visible user/LYRA turns are kept in memory for the current process.
5. **AI tool planning with local authority** — the model may propose only tools advertised by THE OS; THE OS validates the proposal, converts it to a registered `ActionRequest`, executes locally, and reports verified results.

The model never receives arbitrary shell execution. A model tool call is only a proposal. The local `ToolCatalog` is an allowlist and `ActionRegistry` remains the execution authority.

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
