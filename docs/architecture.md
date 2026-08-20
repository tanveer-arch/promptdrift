# Architecture

PromptDrift follows a layered architecture where each module has a single responsibility and communicates through Pydantic models.

## Data Flow

```
promptdrift.yaml          Jinja2 Template         LLM Provider
       │                       │                       │
       ▼                       ▼                       ▼
  ┌─────────┐           ┌───────────┐           ┌───────────┐
  │ Config  │──────────▶│ Templates │──────────▶│ Providers │
  │ Loader  │           │  Renderer │           │  Adapter  │
  └─────────┘           └───────────┘           └─────┬─────┘
       │                                              │
       │  TestCase[]                    ModelResponse  │
       ▼                                              ▼
  ┌──────────────────────────────────────────────────────┐
  │                    Engine (Runner)                    │
  │                                                      │
  │  For each test:                                      │
  │    1. Render prompt template with variables           │
  │    2. Send to provider                               │
  │    3. Evaluate all assertions                        │
  │    4. Check thresholds                               │
  │    5. Determine PASS / WARN / FAIL                   │
  └───────────────┬──────────────────────────────────────┘
                  │
                  │  RegressionReport
                  ▼
  ┌───────────────────────────────────┐
  │        Baseline Comparison        │
  │  (optional, if baseline exists)   │
  │                                   │
  │  - Hash comparison                │
  │  - Diagnostic annotations         │
  │  - New test detection              │
  └───────────────┬───────────────────┘
                  │
                  │  RegressionReport (annotated)
                  ▼
  ┌──────────┬──────────┬──────────┬──────────┐
  │ Terminal │   JSON   │   HTML   │  GitHub  │
  │  Report  │  Output  │  Report  │ Summary  │
  └──────────┴──────────┴──────────┴──────────┘
                  │
                  ▼
  ┌───────────────────────────────────┐
  │     SQLite Local History          │
  │  (best-effort, non-critical)      │
  └───────────────────────────────────┘
```

## Module Responsibilities

### `config.py` — Configuration Loader

Reads `promptdrift.yaml`, validates it against strict Pydantic models, and returns a typed `Config` object. Rejects unknown fields immediately rather than ignoring them.

### `templates.py` — Prompt Renderer

Renders Jinja2 templates in a sandboxed environment. Detects missing variables before rendering and raises clear errors. No filesystem access or code execution from templates.

### `providers/` — LLM Adapters

Each provider (OpenAI, Ollama, Mock) implements a single `complete()` method that returns a normalized `ModelResponse`. Providers handle their own authentication, HTTP calls, and error wrapping.

- **`openai.py`** — Uses `httpx` directly (no SDK dependency). Reads API key from env.
- **`ollama.py`** — Calls the local Ollama API. No authentication needed.
- **`mock.py`** — Echoes the prompt. Zero latency, zero cost, fully deterministic.

### `evaluators/` — Assertion Engine

Evaluates each assertion independently against the model response. Returns an `EvaluationResult` with pass/fail, expected/actual values, and a human-readable reason. Each assertion type is a pure function — no side effects.

### `engine/` — Execution Core

- **`runner.py`** — Orchestrates the test suite: render → call → evaluate → aggregate.
- **`baseline.py`** — Reads and writes baseline files. Baselines store hashes (not raw output).
- **`regression.py`** — Compares current results against a baseline. Annotates changes without causing spurious failures.

### `models/` — Data Contracts

All data flows through Pydantic models with `extra="forbid"`:

- **`config.py`** — `Config`, `ProviderConfig`, `Defaults`, `BaselineConfig`, `CIConfig`
- **`test.py`** — `TestCase`, `Assertion`, `Evaluator`, `Threshold`
- **`result.py`** — `ModelResponse`, `EvaluationResult`, `TestRun`, `RegressionReport`
- **`baseline.py`** — `Baseline`, `BaselineTest`

### `reports/` — Output Formatters

- **`terminal.py`** — Rich tables for the CLI.
- **`html.py`** — Self-contained HTML file with no external dependencies.
- **`github.py`** — Markdown for GitHub Step Summaries and PR comments.

### `storage/` — Local History

SQLite-based local run history. Best-effort only — failures are silently caught. Raw prompts and outputs are suppressed by default for privacy.

## Design Principles

1. **Contracts, not cosmetic diffs.** A wording change is not a failure. Only violated behavioral assertions fail the build.
2. **Privacy by default.** No telemetry, no hosted service, no raw output in baselines. API keys are env-only.
3. **Strict validation.** Unknown config fields are errors, not warnings. Catch mistakes at load time.
4. **Provider isolation.** Adding a new provider requires one file and no changes to the engine.
5. **Deterministic evaluation.** All built-in assertions are deterministic — same input always produces the same pass/fail result.
