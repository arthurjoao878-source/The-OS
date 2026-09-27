# THE OS

Assistant-first Windows environment centered on **LYRA**.

## Current vertical slices

The repository currently proves three independent boundaries:

1. **Verified Windows action** — deterministic intent -> `ActionRegistry` -> Windows adapter -> process verification.
2. **Persistent LYRA memory** — explicit remember/recall intents backed by local SQLite.
3. **Provider-neutral AI conversation boundary** — deterministic actions/memory stay local; unmatched conversation can fall through to a configured AI provider.

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

## Test

```powershell
python -m pytest -q
python -m ruff check .
```
