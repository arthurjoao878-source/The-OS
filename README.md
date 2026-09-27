# THE OS

Assistant-first Windows environment centered on **LYRA**.

## First slice

This repository bootstrap implements one verified real action:

```text
abre o Discord
```

The flow is:

```text
text -> deterministic intent -> ActionRegistry -> Windows adapter -> process verification -> LYRA result
```

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m theos
```

## Test

```powershell
python -m pytest -q
python -m ruff check .
```

The AI provider, persistence, Tasks and voice are intentionally added after the real Action loop is proven.