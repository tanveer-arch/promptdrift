# PromptDrift

[![CI](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml/badge.svg)](https://github.com/tanveer-arch/promptdrift/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/promptdrift-ci?color=blue)](https://pypi.org/project/promptdrift-ci/)
[![Python](https://img.shields.io/pypi/pyversions/promptdrift-ci)](https://pypi.org/project/promptdrift-ci/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Git-native AI behavior change detection.**

### Change a prompt. PromptDrift automatically shows what changed in AI behavior, what broke, what improved, and whether the change is safe to merge.

PromptDrift turns your real application traffic and prompt changes into automatic regression coverage with **Impact Radius analysis**, without requiring manual authoring of dozens of YAML tests.

```text
application / prompt / traffic
          ↓
      discovery
          ↓
   scenario library
          ↓
   baseline behavior
          ↓
 prompt change detected
          ↓
 replay + evaluation
          ↓
 regression analysis
          ↓
 GitHub PR / CLI report
```

---

## 3-Minute Quick Start

```bash
pip install promptdrift-ci
promptdrift init
```

PromptDrift scans your repository context and sets up starter files.

### 1. Capture real or example interactions
```bash
promptdrift capture --input "How do I cancel my order?" --output "You can cancel within 24 hours."
```

### 2. Turn captures into candidate regression scenarios
```bash
promptdrift learn
```

### 3. Review and promote scenarios to the active suite
```bash
promptdrift scenarios
promptdrift suggest cancellation_how_do_i_cancel
promptdrift promote cancellation_how_do_i_cancel
```

### 4. Create your baseline
```bash
promptdrift baseline
```

### 5. Run Git-aware check
```bash
promptdrift check
```

---

## Impact Radius & Behavioral Change Report

When you modify your prompt templates and run `promptdrift check`:

```text
PromptDrift Impact Report
Behavior changed in 8 / 43 scenarios.

  ✓ 5 improved
  ⚪ 35 unchanged
  💬 17 changed but valid
  ✗ 3 regressed

Impact radius: 18.6%
Latency change: +7.2%
Cost change:    +11.3%

Affected Categories:
  Refunds          5 affected
  Cancellation     2 affected
  Escalation       1 affected

Regressions:
  ✗ refund_request
    Required policy condition failed: 30 days window missing.
  ✗ cancellation_001
    JSON schema failed: 'order_id' is a required property.
```

---

## Define Explicit Behavioral Contracts (Advanced Mode)

You can always define explicit behavioral contracts in `promptdrift.yaml`:

```yaml
version: 2

project:
  name: support-bot

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

### Built-in Deterministic Assertions
`exact_match` · `contains` · `not_contains` · `regex` · `not_regex` · `json_valid` · `json_schema` · `min_length` · `max_length` · `max_tokens` · `latency_ms` · `cost_usd`

---

## GitHub Action & PR Workflow

```yaml
name: PromptDrift Check

on:
  pull_request:
    paths:
      - "prompts/**"
      - "promptdrift.yaml"

permissions:
  contents: read
  pull-requests: write

jobs:
  promptdrift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: tanveer-arch/promptdrift/action@v1
        with:
          config: promptdrift.yaml
          comment: 'true'
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

## Complete CLI Command Suite

| Command | Description |
| --- | --- |
| `promptdrift init` | Zero-config setup detecting Git context and prompts |
| `promptdrift capture` | Log application interactions into local storage |
| `promptdrift learn` | Cluster captured interactions into regression candidates |
| `promptdrift scenarios` | List and inspect the local scenario library |
| `promptdrift suggest` | Suggest deterministic contracts for discovered scenarios |
| `promptdrift promote` | Promote candidate scenarios into committed regression tests |
| `promptdrift check` | Git-aware scenario execution and Impact Radius report |
| `promptdrift accept` | Accept intentional behavior updates as the new baseline |
| `promptdrift test` | Run behavioral contracts suite (backward compatible) |
| `promptdrift baseline` | Capture canonical version-controlled baseline |
| `promptdrift diff` | Compare current behavior against baseline |
| `promptdrift report` | Generate offline HTML report |
| `promptdrift purge` | Clear all local capture data |
| `promptdrift doctor` | Validate config, prerequisites, and privacy status |
| `promptdrift version` | Print version |

---

## Privacy by Default

- **No telemetry, tracking, or cloud accounts**
- Prompts are evaluated against the provider you configure
- Captured traffic remains local in SQLite and is excluded from Git by default
- Baseline files store hashes and metrics, never raw user inputs or prompt secrets
- Clean wipe available at any time via `promptdrift purge`

---

## License

Released under the [MIT License](LICENSE).
