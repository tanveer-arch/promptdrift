# PromptDrift

[![CI](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/promptdrift-ci?color=blue)](https://pypi.org/project/promptdrift-ci/)
[![Python](https://img.shields.io/pypi/pyversions/promptdrift-ci)](https://pypi.org/project/promptdrift-ci/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

### CI regression testing for LLM prompts.

**Catch AI behavior regressions before they reach production.**

PromptDrift turns the behavior you need from a prompt into explicit, reviewable contracts. When a prompt changes, it runs those contracts in CI and tells you exactly what broke — without treating every wording change as a regression.

```text
prompt change  →  PromptDrift  →  behavioral contracts  →  PR check
                                                        ↳ PASS · WARN · FAIL
```

## Why PromptDrift?

`git diff` tells you what changed in the prompt text. **PromptDrift tells you whether the AI behavior changed in a way that matters.**

| Problem | PromptDrift's answer |
| --- | --- |
| "We changed a prompt and broke 3 customer flows" | Behavioral contracts catch regressions before merge |
| "Every LLM output is different — how do I test that?" | Test structure and constraints, not exact wording |
| "Our prompt tests are flaky because they diff raw output" | Contracts pass/fail deterministically on semantics |
| "We have no idea if a prompt change is safe to deploy" | CI gives a clear PASS/FAIL on every PR |

## Quick Start

```bash
pip install promptdrift-ci
promptdrift init
promptdrift test
```

`init` creates a fully local example using the deterministic `mock` provider. No API key needed — validate the workflow first, then connect OpenAI or Ollama.

Capture approved behavior:

```bash
promptdrift baseline
git add promptdrift.baseline.json
```

## Define Behavioral Contracts

`promptdrift.yaml` stays small, readable, and version-controlled:

```yaml
version: 1

provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY

tests:
  - id: refund_request
    prompt: prompts/support.txt
    variables:
      policy: Refunds are available within 30 days.
      question: Can I get a refund for my order?
    assertions:
      - type: contains
        value: 30 days
      - type: not_contains
        value: guaranteed
      - type: max_length
        value: 600
```

```text
❌ FAIL refund_request

Assertion: contains
Expected: 30 days
Actual:   You may be eligible for a refund.
Reason:   Required text does not appear in the output.
```

## Contracts, Not Cosmetic Diffs

| PromptDrift fails when… | PromptDrift does **not** fail just because… |
| --- | --- |
| Required text disappears | Wording changes |
| Forbidden content appears | Sentence order changes |
| JSON is invalid or violates its schema | An otherwise-valid answer is phrased differently |
| A length, token, latency, or cost limit is exceeded | Output hashes differ but contracts still pass |

### Built-in Assertions

`exact_match` · `contains` · `not_contains` · `regex` · `not_regex` · `json_valid` · `json_schema` · `min_length` · `max_length` · `max_tokens` · `latency_ms` · `cost_usd`

Each assertion supports `severity: warn` for non-blocking warnings.

## Run in CI

```yaml
name: PromptDrift

on:
  pull_request:
    paths:
      - "prompts/**"
      - "promptdrift.yaml"

permissions:
  contents: read

jobs:
  promptdrift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: tanveer-arch/promptdrift/action@v1
        with:
          config: promptdrift.yaml
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The Action writes a Step Summary, uploads a JSON report, and fails only after reports are available. For PR comments, add `comment: 'true'` and grant `pull-requests: write`.

> **Security:** Use `pull_request` for untrusted forks. Never expose provider secrets with `pull_request_target` while executing code from a pull request.

## Commands

| Command | What it does |
| --- | --- |
| `promptdrift init` | Creates an offline starter suite |
| `promptdrift test` | Runs contracts; auto-compares against baseline |
| `promptdrift baseline` | Captures approved behavior (requires `--force` to replace) |
| `promptdrift diff` | Runs and compares current output with baseline |
| `promptdrift report` | Generates an offline HTML report |
| `promptdrift doctor` | Checks config, files, keys, and baseline health |
| `promptdrift version` | Prints the installed version |

All commands support `--json` for machine-readable output. Exit codes: `0` success, `1` behavioral failure, `2` config/usage error, `3` provider/runtime error.

## Architecture

```
promptdrift.yaml ─→ Config ─→ Template ─→ Provider ─→ Evaluator ─→ Report
                     Loader    Renderer    Adapter     Engine       Formatter
                                                        │
                                                  Baseline ←── Git
                                                  Comparison
```

- **Providers** are isolated adapters (OpenAI, Ollama, Mock) — adding one is a single file
- **Assertions** are pure, deterministic functions — same input always produces the same result
- **Baselines** store hashes and metrics, never raw outputs or secrets
- **Reports** output to terminal, JSON, HTML, or GitHub PR comments

## Privacy by Default

- **No telemetry, accounts, or hosted service**
- Prompt content goes only to the provider you configure
- API keys are environment variables — never config values
- Baselines contain hashes and metrics, not raw outputs
- Local SQLite history suppresses prompts and outputs by default

## Documentation

| Guide | Description |
| --- | --- |
| [Getting Started](docs/getting-started.md) | Install, first run, and connecting a provider |
| [Configuration](docs/configuration.md) | Full `promptdrift.yaml` reference |
| [Assertions](docs/assertions.md) | All contract types with examples |
| [Providers](docs/providers.md) | OpenAI, Ollama, and Mock setup |
| [Baselines](docs/baselines.md) | Create, compare, and update baselines |
| [GitHub Action](docs/github-action.md) | CI setup, secrets, and fork security |
| [Architecture](docs/architecture.md) | Module design and data flow |
| [FAQ](docs/faq.md) | Common questions and troubleshooting |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, and PR process |

## Roadmap

- [ ] Semantic similarity assertions (embedding-based)
- [ ] LLM-as-judge evaluator
- [ ] Multi-provider comparison (same prompt, different models)
- [ ] Parallel test execution
- [ ] PyPI trusted publisher release
- [ ] Cost tracking dashboard

## License

Released under the [MIT License](LICENSE).
