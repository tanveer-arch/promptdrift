# PromptDrift

[![CI](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml)

### CI regression testing for LLM prompts.

**Catch AI behavior regressions before they reach production.**

PromptDrift turns the behavior you need from a prompt into explicit, reviewable contracts. When a prompt changes, it runs those contracts in CI and tells you exactly what broke—without treating every wording change as a regression.

```text
prompt change  →  PromptDrift  →  behavioral contracts  →  PR check
                                                        ↳ PASS · WARN · FAIL
```

```text
❌ Regression detected: support_json

json_schema
Missing required property: escalation_required

The PR check failed before the change reached production.
```

## Start in 30 seconds

```bash
pip install promptdrift
promptdrift init
promptdrift test
```

`init` creates a fully local example using the deterministic `mock` provider. It needs no API key, so you can validate the workflow before connecting OpenAI or Ollama.

Then capture approved behavior in Git:

```bash
promptdrift baseline
git add promptdrift.baseline.json
```

## Describe the behavior that matters

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

## Contracts, not cosmetic diffs

| PromptDrift fails when… | PromptDrift does not fail just because… |
| --- | --- |
| required text disappears | wording changes |
| forbidden content appears | sentence order changes |
| JSON is invalid or violates its schema | an otherwise-valid answer is phrased differently |
| a length, token, latency, or cost limit is exceeded | output hashes differ but contracts still pass |

Built-in deterministic assertions: `exact_match`, `contains`, `not_contains`, `regex`, `not_regex`, `json_valid`, `json_schema`, `min_length`, `max_length`, `max_tokens`, `latency_ms`, and `cost_usd`.

## Add it to a pull request

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

The Action writes a concise Step Summary, uploads a machine-readable JSON report, and fails only after reports are available. For optional PR comments, add `comment: 'true'` and grant `pull-requests: write`.

> Security: use `pull_request` for untrusted forks. Never expose provider secrets with `pull_request_target` while executing code from a pull request.

## Commands

| Command | What it does |
| --- | --- |
| `promptdrift init` | Creates an offline starter suite. |
| `promptdrift test` | Runs contracts; compares an existing baseline automatically. |
| `promptdrift baseline` | Captures approved behavior; requires `--force` to replace. |
| `promptdrift diff` | Runs and compares the current result with the baseline. |
| `promptdrift report` | Writes an offline HTML report. |
| `promptdrift doctor` | Checks configuration, files, keys, and baseline health. |

Every execution command supports `--json`; use `--verbose` for debugging. Exit codes are stable: `0` success, `1` behavioral failure, `2` configuration/usage error, `3` provider/runtime error.

## Privacy by default

PromptDrift has no hosted service, telemetry, accounts, or remote database. Prompt content goes only to the provider you configure. API keys are environment variables, never config values; canonical baselines contain hashes and metrics—not secrets or raw outputs. Local SQLite history suppresses prompts and outputs by default.

## Learn more

- [Getting started](docs/getting-started.md)
- [Configuration](docs/configuration.md)
- [Assertions](docs/assertions.md)
- [Providers](docs/providers.md)
- [Baselines](docs/baselines.md)
- [GitHub Action](docs/github-action.md)
- [Architecture](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)

Released under the [MIT License](LICENSE).
