# Architecture

PromptDrift follows a layered, modular architecture designed for local-first execution, Git-native CI workflows, and zero-telemetry privacy.

## Data Flow

```
Traffic / Interaction ───▶ Capture Ingestion ───▶ Discovery (`learn`) ───▶ Scenario Library (.promptdrift/scenarios.json)
                                                                                   │
                                                                                   ▼
promptdrift.yaml ───────▶ Config Loader ──────────────────────────────────▶ Runner Engine
                                                                                   │
                                                                           Provider Adapter (OpenAI/Ollama/Mock)
                                                                                   │
                                                                             ModelResponse
                                                                                   │
                                                                           Evaluators (Assertions + Semantic)
                                                                                   │
                                                                                   ▼
                                                                           RegressionReport
                                                                                   │
                                           Git Context (diff/base) ───────────────┼─────────────── Baseline Store (v1/v2)
                                                                                   │
                                                                                   ▼
                                                                        Impact Radius Engine
                                                                                   │
                                                                    ┌──────────────┼──────────────┐
                                                                    ▼              ▼              ▼
                                                               Terminal CLI   JSON / HTML   GitHub Step Summary / PR Comment
```

## Module Responsibilities

### `git.py` — Git Context & Diffing
Discovers git repository root, detects current branch and commit SHA, and identifies modified prompt templates relative to Git base refs (e.g. `origin/main` vs `HEAD`).

### `models/` — Data Contracts
- **`config.py`** — Validates `promptdrift.yaml` supporting `version: 1` and `version: 2`.
- **`capture.py`** — `Interaction`, `Scenario`, and `ScenarioLibrary`.
- **`baseline.py`** — Strict `Baseline` schema v2 with backward-compatible v1 migration.
- **`result.py`** — `ModelResponse`, `EvaluationResult`, `TestRun`, and `RegressionReport`.

### `engine/` — Core Execution & Analysis
- **`runner.py`** — Renders templates, calls providers, evaluates contracts, and aggregates runs.
- **`capture.py`** — Sanitizes and records local interactions for future learning.
- **`discovery.py`** — Deterministically clusters raw interactions into candidate scenarios (`promptdrift learn`).
- **`suggest.py`** — Automatically derives contract suggestions (JSON validity, schema, length bounds, policy rules).
- **`check.py`** — Orchestrates Git-aware selective test execution and computes impact radius.

### `impact.py` — Impact Radius & Classification
Categorizes before/after behavioral deltas into `REGRESSED`, `IMPROVED`, `UNCHANGED`, `CHANGED_BUT_VALID`, `NEW`, and `MISSING`. Computes aggregate latency and cost deltas.

### `storage/` — Local State
- **`sqlite.py`** — Local SQLite storage for interaction logs and run history (never committed to Git).
- **`scenarios.py`** — Versioned JSON scenario store (`.promptdrift/scenarios.json`).

### `reports/` — Output Formatters
- **`terminal.py`** & **`impact_report.py`** — Rich CLI tables and impact summaries.
- **`github.py`** — Markdown formatted for GitHub Action Step Summaries and deduplicating PR comments.
- **`html.py`** — Standalone, offline HTML report.
