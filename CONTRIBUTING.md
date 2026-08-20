# Contributing to PromptDrift

Thank you for your interest in improving PromptDrift! This guide covers everything you need to get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/tanveer-arch/promptdrift.git
cd promptdrift

# Install with development dependencies
pip install -e ".[dev]"

# Verify the setup
pytest
ruff check src tests
```

## Project Structure

```
src/promptdrift/
├── cli.py              # Typer CLI commands
├── config.py           # YAML config loader
├── templates.py        # Jinja2 prompt renderer
├── errors.py           # Exception hierarchy
├── engine/             # Test runner, baselines, regression
├── evaluators/         # Deterministic assertion evaluators
├── models/             # Pydantic data models
├── providers/          # LLM adapters (OpenAI, Ollama, Mock)
├── reports/            # Terminal, HTML, GitHub formatters
└── storage/            # SQLite local history

tests/
├── unit/               # Fast, isolated tests
├── integration/        # CLI end-to-end tests
├── fixtures/           # Shared test data
└── snapshots/          # Output snapshot tests
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/unit/test_evaluators.py

# Run tests matching a pattern
pytest -k "test_contains"

# Run with coverage
pytest --cov=promptdrift --cov-report=term-missing
```

## Code Style

PromptDrift uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for lint errors
ruff check src tests

# Auto-fix what's possible
ruff check --fix src tests
```

**Style guidelines:**
- Line length: 100 characters
- Target Python: 3.11+
- Lint rules: `E`, `F`, `I` (imports), `UP` (pyupgrade)
- All models use `ConfigDict(extra="forbid")` — no silent field drops
- Provider errors never expose request bodies or credentials

## Making Changes

### 1. Pick an Issue or Feature

Check [open issues](https://github.com/tanveer-arch/promptdrift/issues) or create a new one describing what you want to work on.

### 2. Create a Branch

```bash
git checkout -b feat/your-feature-name
```

Use prefixes: `feat/`, `fix/`, `docs/`, `test/`, `refactor/`.

### 3. Write Tests First

PromptDrift is a testing tool — tests are not optional. For any behavioral change:
- Add unit tests in `tests/unit/`
- Add integration tests in `tests/integration/` for CLI changes
- Ensure edge cases are covered

### 4. Make Your Changes

Follow the existing patterns:
- Providers implement the `Provider` ABC
- All data flows through Pydantic models
- Errors use the `PromptDriftError` hierarchy
- Keep providers isolated from the engine

### 5. Verify

```bash
pytest
ruff check src tests
```

### 6. Submit a Pull Request

- Write a clear description of what changed and why
- Link related issues
- Ensure CI passes

## Architecture Guidelines

- **Providers are isolated.** A new provider is one file + a type registration. It should never import engine internals.
- **Assertions are pure functions.** Each evaluator takes an assertion and a response, returns a result. No side effects.
- **Config compatibility is sacred.** Never break existing `promptdrift.yaml` files. New fields must have defaults.
- **Privacy by default.** Never log, store, or transmit raw prompt content unless the user explicitly opts in.

## Reporting Bugs

Use the [bug report template](https://github.com/tanveer-arch/promptdrift/issues/new?template=bug_report.yml) and include:
- PromptDrift version (`promptdrift version`)
- Python version (`python --version`)
- OS and provider
- Steps to reproduce
- Expected vs actual behavior

## Questions?

Open a [discussion](https://github.com/tanveer-arch/promptdrift/discussions) or reach out on the issue tracker.
