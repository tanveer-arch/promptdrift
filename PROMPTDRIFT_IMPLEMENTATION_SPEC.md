# PromptDrift — Implementation Specification for Claude Code

> **Purpose:** This document is the authoritative build specification for PromptDrift.
> Give this file to Claude Code as the implementation brief. Claude should build the repository from this specification, not invent a broader product.
>
> **Project goal:** Build a polished, open-source, local-first developer tool that catches unintended changes in LLM behavior in GitHub workflows before they reach production.
>
> **Primary positioning:**  
> **PromptDrift = CI regression testing for LLM prompts.**
>
> **Core promise:**  
> Git diff tells developers what changed in the prompt. PromptDrift tells them whether the AI behavior changed in a way that matters.

---

# 1. Product Definition

PromptDrift is a Python CLI + GitHub Action for regression-testing LLM prompts.

A developer stores prompts and test cases in their repository. PromptDrift executes those test cases against an LLM provider, evaluates the results, compares them with a baseline, and produces a human-readable pass/fail report.

The primary workflow is:

```text
Developer changes prompt
        ↓
Git commit / Pull Request
        ↓
GitHub Action
        ↓
PromptDrift runs regression tests
        ↓
Compare current behavior with expected/baseline behavior
        ↓
PASS / WARN / FAIL
        ↓
PR summary with affected test cases
```

PromptDrift must NOT initially become:

- a full LLM observability platform
- a hosted SaaS dashboard
- a general-purpose AI agent framework
- a prompt marketplace
- a prompt optimization service
- a generic tracing platform

The product should remain narrow and excellent at prompt/LLM regression testing.

The attached original plan establishes the local-first CLI, PyPI packaging, provider abstraction, SQLite/reporting ideas, and GitHub Action direction. fileciteturn0file0L5-L13

The original plan currently proposes similarity, length, tone, cost, and latency metrics. Those should NOT all be treated as equivalent measures of behavioral drift. Similarity/length/tone are useful diagnostics, but the central product must judge whether the output still satisfies the developer's declared contract.

---

# 2. Product Principles

Claude must follow these principles while implementing the project.

## 2.1 Correctness before cleverness

Prefer deterministic checks over vague AI scoring whenever possible.

Examples:

- JSON schema validation
- exact match
- contains / not_contains
- regex
- required fields
- forbidden phrases
- token/character limits
- latency thresholds
- cost thresholds

LLM-as-a-judge evaluation may exist, but it must be explicitly opt-in and clearly labeled as probabilistic.

## 2.2 CI-first

The GitHub Action is a first-class product surface, not a later add-on.

A developer should be able to go from:

```bash
pip install promptdrift
```

to:

```bash
promptdrift init
promptdrift test
```

and then to a GitHub Action with minimal configuration.

## 2.3 Local-first and privacy-conscious

By default:

- no telemetry
- no hosted service
- no user prompts uploaded to PromptDrift
- no external database
- no accounts
- no mandatory dashboard

The only external data transmission should be to the configured LLM provider or explicitly configured evaluator.

The original research identified privacy and secrets management as important for CI use, especially around GitHub Actions. fileciteturn0file0L215-L220

## 2.4 Git-native

Tests, prompts, configuration, and baselines should be easy to review in Git.

The product should work naturally with:

```text
git diff
pull requests
GitHub Actions
code review
branch comparison
```

## 2.5 Great CLI UX

The CLI should feel like a serious developer tool.

Use:

- clear commands
- useful errors
- exit codes
- concise terminal output
- Rich tables/panels where appropriate
- `--json` for machine-readable output
- `--verbose` for debugging
- colors that are optional and disabled when output is not a TTY

The original plan selected Typer + Rich for this reason. fileciteturn0file0L101-L111

---

# 3. Competitive Positioning

PromptDrift exists in a crowded LLM evaluation/observability ecosystem.

The implementation must therefore preserve a narrow differentiator:

> **PromptDrift is the lightweight Git-native regression gate for LLM behavior.**

Relevant existing categories include:

- Promptfoo — broad prompt/LLM testing and red teaming
- Langfuse — observability, evaluations, prompt management
- Ragas — evaluation, particularly RAG
- Arize Phoenix — observability and evaluation
- Helicone — gateway/observability
- Latitude/Pezzo/other LLMOps tools — broader platform workflows

The research found that broad platforms already cover many general evaluation and observability capabilities. PromptDrift should win through simplicity, CI-native workflows, low setup friction, and excellent regression explanations.

There is also already at least one small project with a similar “prompt drift” concept, so PromptDrift must avoid merely cloning a one-command output-change detector. Differentiation should come from a strong declarative test contract, useful baseline comparisons, structured-output validation, PR reporting, and excellent developer UX.

The research specifically found Promptfoo to be a major adjacent competitor and GitHub-native LLM testing to be an established workflow pattern. fileciteturn0file0L19-L28

---

# 4. Feature Priority

## 4.1 MUST-HAVE

These features define the initial release.

### A. PromptDrift CLI

Install:

```bash
pip install promptdrift
```

Also support:

```bash
uvx promptdrift
```

The original plan explicitly targeted both PyPI and `uvx`. fileciteturn0file0L9-L13

Commands:

```text
promptdrift init
promptdrift test
promptdrift baseline
promptdrift diff
promptdrift doctor
promptdrift version
```

Do not create a huge command surface in v1.

---

### B. Declarative test configuration

Use a human-readable YAML configuration.

Recommended default file:

```text
promptdrift.yaml
```

Example:

```yaml
version: 1

provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY

defaults:
  temperature: 0
  max_output_tokens: 500

tests:
  - id: refund_request
    prompt: prompts/support.txt
    variables:
      customer_message: "Can I get a refund?"

    assertions:
      - type: contains
        value: "refund"

      - type: not_contains
        value: "guaranteed"

    thresholds:
      latency_ms: 3000

  - id: support_json
    prompt: prompts/support_json.txt
    variables:
      customer_message: "My order is late."

    output:
      format: json

    assertions:
      - type: json_schema
        schema:
          type: object
          required:
            - answer
            - escalation_required
          properties:
            answer:
              type: string
            escalation_required:
              type: boolean
```

The schema must be designed for readability and future compatibility.

---

### C. Prompt templates

Prompt files should be external to the YAML whenever practical.

Example:

```text
prompts/
  support.txt
  summarizer.txt
  sql_agent.txt
```

Template variables:

```text
You are a customer-support assistant.

Customer message:
{{ customer_message }}

Return a concise answer.
```

Use a safe, deterministic templating mechanism.

Do not allow arbitrary Python execution inside prompt templates.

---

### D. Provider abstraction

Create a clean provider interface.

Initial providers:

1. OpenAI
2. Ollama

Provider support must be abstracted so additional providers can later be added without changing the evaluation engine.

The original plan proposed LiteLLM for broad provider access. fileciteturn0file0L103-L110

Implementation guidance:

- A provider adapter interface is required.
- LiteLLM may be used internally if it materially reduces maintenance.
- Do not make LiteLLM-specific concepts leak throughout the application.
- Provider failures must be normalized into PromptDrift errors.

Environment variables:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
```

Only expose environment variables for providers that are actually implemented.

---

### E. Deterministic assertion engine

This is one of the most important components.

Implement:

```text
exact_match
contains
not_contains
regex
not_regex
json_valid
json_schema
min_length
max_length
max_tokens
latency_ms
cost_usd
```

Assertions should produce structured results:

```json
{
  "passed": false,
  "assertion": "json_schema",
  "expected": "...",
  "actual": "...",
  "reason": "Missing required property: escalation_required"
}
```

A single failed critical assertion can make the test fail.

---

### F. Baseline system

PromptDrift must support a version-controlled baseline.

Preferred model:

```text
promptdrift.baseline.json
```

The baseline records:

- Prompt/test identity
- provider/model
- relevant runtime settings
- output hash
- assertion results
- evaluation metrics
- timestamp
- PromptDrift version

Do NOT make the baseline depend exclusively on a hidden SQLite database.

A developer should be able to review baseline changes in Git.

Example:

```bash
promptdrift baseline
```

creates/updates:

```text
promptdrift.baseline.json
```

Then:

```bash
promptdrift test
```

compares the current run to the baseline.

---

### G. Regression detection

Distinguish:

```text
PASS
WARN
FAIL
```

Example semantics:

**PASS**
- All required assertions pass.
- No configured regression threshold is exceeded.

**WARN**
- Output changed materially but no declared behavioral contract was violated.
- Diagnostic metrics changed.
- Non-blocking thresholds were crossed.

**FAIL**
- A required assertion fails.
- A critical regression threshold is exceeded.

Do not fail a build merely because wording changed.

This is a core product rule.

---

### H. Useful semantic comparison

Implement semantic/output comparison in layers.

Layer 1 — deterministic assertions.

Layer 2 — structural comparison:

- JSON keys
- list length
- required fields
- output length
- normalized text

Layer 3 — optional semantic evaluation:

- embedding similarity
- LLM-as-a-judge

The semantic evaluator must never silently become the sole source of truth.

The original research noted that naive hallucination/similarity metrics can be arbitrary or misleading without appropriate reference data. fileciteturn0file0L217-L220

---

### I. Human-readable CLI report

Example:

```text
PromptDrift
────────────────────────────────────────────────────────────

Suite: support
Model: gpt-4.1-mini
Tests: 24

  PASS   21
  WARN    2
  FAIL    1

Regression detected.

FAIL  support_json
      json_schema
      Missing required property: escalation_required

WARN  refund_request
      Output changed significantly
      All behavioral assertions still pass

────────────────────────────────────────────────────────────
21 passed • 2 warnings • 1 failed
Baseline: promptdrift.baseline.json
```

Use Rich for terminal presentation.

---

### J. GitHub Action

Provide a reusable GitHub Action.

Target user experience:

```yaml
name: PromptDrift

on:
  pull_request:
    paths:
      - "prompts/**"
      - "promptdrift.yaml"
      - "tests/**"

jobs:
  promptdrift:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: promptdrift/action@v1
        with:
          config: promptdrift.yaml
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The action must:

1. install/run PromptDrift
2. execute tests
3. produce a GitHub Actions summary
4. fail the workflow on configured FAIL conditions
5. optionally create/update a PR comment
6. expose machine-readable artifacts

The research confirms that PR-triggered LLM testing and workflow summaries are established CI patterns. fileciteturn0file0L179-L188

---

### K. PR comment

A high-quality PR comment is a major adoption feature.

Example:

```text
## PromptDrift

❌ Regression detected

| Test | Status | Reason |
|------|--------|--------|
| refund_request | ✅ | All assertions passed |
| support_json | ❌ | JSON schema failed |
| escalation | ⚠️ | Semantic similarity dropped |

### Summary

21 passed · 2 warnings · 1 failed

Baseline: `main`
Current: `feature/update-support-prompt`

[View full PromptDrift report]
```

Do not spam comments.

The Action should update an existing PromptDrift comment when possible.

---

### L. JSON output

Every major command should support:

```bash
promptdrift test --json
```

Output must be deterministic and machine-readable.

This makes PromptDrift usable by other automation systems.

---

### M. Doctor command

Implement:

```bash
promptdrift doctor
```

Check:

- PromptDrift installation
- config existence
- YAML validity
- provider API key presence
- provider connectivity
- baseline readability
- prompt file references
- output directory writability
- dependency problems

Example:

```text
PromptDrift Doctor

✓ Config found
✓ YAML valid
✓ OPENAI_API_KEY found
✓ OpenAI reachable
✓ Baseline valid
✓ 12 test cases discovered

Ready.
```

---

### N. Tests

The PromptDrift repository itself must have strong automated tests.

Required categories:

- config parsing
- template rendering
- provider adapters
- assertion engine
- JSON schema validation
- baseline generation
- baseline comparison
- regression classification
- CLI behavior
- exit codes
- JSON output
- GitHub Action packaging

Avoid making unit tests call live LLM APIs.

Use mocks and deterministic fixtures.

Provide a small optional integration test suite.

---

### O. Documentation

Repository must include at minimum:

```text
README.md
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
LICENSE
CHANGELOG.md
docs/
  getting-started.md
  configuration.md
  assertions.md
  providers.md
  github-action.md
  baselines.md
  architecture.md
  faq.md
```

README must immediately explain:

1. What PromptDrift does
2. Why normal tests are insufficient for LLM behavior
3. 30-second install
4. minimal example
5. GitHub Action example
6. real regression example
7. architecture
8. contribution instructions

---

## 4.2 SHOULD-HAVE

Implement these only after the MUST-HAVE architecture is stable.

### A. Cost regression

Calculate provider/model cost where pricing can be represented reliably.

Output:

```text
Cost
$0.12 → $0.19
+58%
```

Important:

- pricing must be versioned
- allow configuration overrides
- never present estimated cost as exact billing

The original plan already identified provider pricing drift as a maintenance risk. fileciteturn0file0L217-L220

---

### B. Latency regression

Store:

- latency_ms
- time-to-first-token if available
- total duration

Allow:

```yaml
thresholds:
  latency_ms:
    warn: 2000
    fail: 5000
```

---

### C. Multi-model comparison

Command:

```bash
promptdrift compare --models gpt-4.1-mini,llama3.2
```

Show:

```text
                 GPT-4.1 Mini   Llama 3.2
Pass rate             96%          91%
JSON validity        100%          94%
Avg latency         1.2s          0.7s
Avg cost            $0.04         local
```

The original plan proposed multi-model comparison, but it should remain secondary to regression CI. fileciteturn0file0L184-L190

---

### D. Rich HTML report

Generate:

```bash
promptdrift report
```

The report should include:

- summary
- test-by-test results
- baseline/current comparison
- changed outputs
- failed assertions
- metrics
- model/provider metadata

Report must work offline.

Do not create a web server.

---

### E. Run history

A local SQLite database may be used for optional history.

Important architectural rule:

**SQLite is for local history/analytics, not the canonical Git baseline.**

Suggested location:

```text
~/.promptdrift/promptdrift.db
```

The original build plan proposed SQLite in the local data directory. fileciteturn0file0L41-L51

---

### F. Embedding-based semantic similarity

Add as an optional evaluator.

Never download a large model during normal startup without informing the user.

Support:

```yaml
evaluators:
  - semantic_similarity
```

Make the evaluator pluggable.

---

### G. LLM-as-a-judge

Optional configuration:

```yaml
evaluators:
  - name: llm_judge
    provider: openai
    model: gpt-4.1-mini
```

The judge should return structured criteria:

```json
{
  "score": 0.92,
  "reason": "...",
  "passed": true
}
```

Clearly mark judge results as probabilistic.

---

### H. Prompt-change detection

On CI, detect which prompts/tests changed.

Only run affected tests by default when safely possible.

Provide:

```bash
promptdrift test --all
promptdrift test --changed
```

Default CI mode may use `--changed` if the repository contains a reliable mapping.

---

### I. Git-aware baseline selection

Support concepts such as:

```bash
promptdrift diff --base main
```

and compare the current branch against baseline metadata.

Do not over-engineer this in the first implementation.

---

### J. Badges

Optional generated badge:

```markdown
![PromptDrift](...)
```

Badge states:

```text
Passing
Warnings
Failing
```

Do not build a hosted badge service for the initial version.

---

### K. Example applications

Create at least 3 example repositories/examples:

```text
examples/
  customer-support/
  structured-json/
  summarization/
```

Each should be copy-paste runnable.

---

# 5. DO NOT BUILD IN THE INITIAL VERSION

Explicitly avoid these unless there is a strong architectural reason.

- hosted dashboard
- user accounts
- SaaS backend
- remote PromptDrift database
- team workspaces
- Slack integration
- Jira integration
- email notifications
- VS Code extension
- prompt marketplace
- automated prompt rewriting
- autonomous test generation
- full agent tracing
- OpenTelemetry ingestion
- full RAG observability
- production telemetry
- complicated plugin marketplace

These are future opportunities, not initial scope.

---

# 6. Recommended Repository Structure

Use this structure as the starting point:

```text
promptdrift/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── promptdrift.yaml.example
│
├── src/
│   └── promptdrift/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── errors.py
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── test.py
│       │   ├── result.py
│       │   └── baseline.py
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── openai.py
│       │   └── ollama.py
│       │
│       ├── evaluators/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── exact_match.py
│       │   ├── text.py
│       │   ├── regex.py
│       │   ├── json_schema.py
│       │   ├── similarity.py
│       │   ├── judge.py
│       │   ├── latency.py
│       │   └── cost.py
│       │
│       ├── engine/
│       │   ├── runner.py
│       │   ├── evaluator.py
│       │   ├── baseline.py
│       │   └── regression.py
│       │
│       ├── storage/
│       │   ├── sqlite.py
│       │   └── filesystem.py
│       │
│       ├── reports/
│       │   ├── terminal.py
│       │   ├── json.py
│       │   └── html.py
│       │
│       └── github/
│           ├── summary.py
│           └── pr_comment.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── snapshots/
│
├── examples/
│   ├── customer-support/
│   ├── structured-json/
│   └── summarization/
│
├── docs/
│   ├── getting-started.md
│   ├── configuration.md
│   ├── assertions.md
│   ├── providers.md
│   ├── baselines.md
│   ├── github-action.md
│   ├── architecture.md
│   └── faq.md
│
├── action/
│   └── action.yml
│
└── .github/
    ├── workflows/
    │   ├── ci.yml
    │   └── release.yml
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md
```

The existing plan already separates CLI, storage, runner, metrics, reporting, diffing, CI, tests, docs, and an Action wrapper. Preserve that modular approach while refocusing the implementation around deterministic evaluation and Git baselines. fileciteturn0file0L55-L95

---

# 7. Core Domain Model

Define explicit Python models.

Conceptually:

```text
Config
 ├── ProviderConfig
 ├── Defaults
 └── TestCase[]

TestCase
 ├── id
 ├── prompt
 ├── variables
 ├── output config
 ├── assertions[]
 ├── evaluators[]
 └── thresholds

TestRun
 ├── test_id
 ├── provider
 ├── model
 ├── input
 ├── output
 ├── latency
 ├── token usage
 ├── estimated cost
 └── evaluation results

EvaluationResult
 ├── status
 ├── score
 ├── expected
 ├── actual
 └── explanation

Baseline
 ├── metadata
 └── test results[]

RegressionReport
 ├── summary
 ├── test results
 ├── regressions
 └── diagnostics
```

Use Pydantic or typed dataclasses where appropriate.

Models should remain serializable.

---

# 8. Configuration Specification

Support a top-level schema like:

```yaml
version: 1

provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY

defaults:
  temperature: 0
  max_output_tokens: 500

baseline:
  path: promptdrift.baseline.json

ci:
  fail_on:
    - assertion_failure
  warn_on:
    - semantic_change
    - latency_regression

tests:
  - id: example
    prompt: prompts/example.txt

    variables:
      input: "Hello"

    assertions:
      - type: contains
        value: "Hello"

    evaluators:
      - type: similarity
        threshold: 0.85

    thresholds:
      latency_ms:
        warn: 2000
        fail: 5000
```

Config validation must be strict and produce actionable error messages.

---

# 9. Assertion/Evaluator Architecture

Use a common evaluator interface.

Conceptually:

```python
class Evaluator(Protocol):
    name: str

    def evaluate(
        self,
        context: EvaluationContext,
        response: ModelResponse,
    ) -> EvaluationResult:
        ...
```

Each evaluator must be independently testable.

Evaluator results should not be tied to terminal formatting.

---

# 10. Regression Logic

Regression logic is central.

The system must distinguish:

### Output changed

This is not automatically a failure.

### Behavior changed

This means a declared contract or important evaluation criterion changed.

### Performance changed

Latency/cost/token use changed.

### Contract violation

A required assertion failed.

Example:

```text
Prompt wording changed
        ↓
Model output changed
        ↓
JSON still valid
required fields still present
business assertions still pass
        ↓
PASS + optional diagnostic
```

But:

```text
Prompt wording changed
        ↓
Model output changed
        ↓
required field disappeared
        ↓
FAIL
```

This distinction is what makes PromptDrift more useful than a simple output-diff tool.

---

# 11. Baseline Format

Use a stable, human-readable JSON format.

Example:

```json
{
  "schema_version": 1,
  "promptdrift_version": "0.1.0",
  "generated_at": "2026-08-19T00:00:00Z",
  "provider": {
    "type": "openai",
    "model": "gpt-4.1-mini"
  },
  "tests": {
    "refund_request": {
      "output_hash": "...",
      "status": "passed",
      "assertions": {
        "contains_refund": true,
        "no_guarantee": true
      }
    }
  }
}
```

Never store API keys.

Never require users to commit raw sensitive responses.

Provide a configuration option to avoid storing raw output in local history.

---

# 12. CLI Specification

Implement these commands.

## `promptdrift init`

Creates:

```text
promptdrift.yaml
prompts/
tests/ (optional)
```

Should provide an interactive mode and a non-interactive mode.

---

## `promptdrift test`

Run tests.

Examples:

```bash
promptdrift test
promptdrift test --config promptdrift.yaml
promptdrift test --json
promptdrift test --verbose
promptdrift test --all
```

Exit codes:

```text
0 = pass
1 = test/regression failure
2 = configuration/usage error
3 = provider/runtime error
```

Keep exit codes documented and stable.

---

## `promptdrift baseline`

Create/update baseline.

Examples:

```bash
promptdrift baseline
promptdrift baseline --force
```

Never silently overwrite a baseline without clear confirmation unless `--force` is passed.

---

## `promptdrift diff`

Compare the current run against baseline.

Example:

```bash
promptdrift diff
```

Output should identify:

- changed tests
- failed assertions
- warnings
- output-level differences
- latency/cost changes
- semantic changes
- overall verdict

---

## `promptdrift doctor`

Run environment diagnostics.

---

## `promptdrift version`

Print version.

---

# 13. GitHub Action Design

The Action should be easy to consume.

Preferred:

```yaml
- uses: promptdrift/action@v1
  with:
    config: promptdrift.yaml
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Requirements:

- pin dependencies
- support configuration path
- support working directory
- expose fail behavior
- write `$GITHUB_STEP_SUMMARY`
- support PR comments
- never print secrets
- do not execute untrusted code with elevated permissions
- clearly document secure workflow configuration

GitHub security is especially important for pull requests from forks. Do not design the Action around `pull_request_target` in a way that executes untrusted PR code with privileged credentials.

The research specifically highlighted this risk. fileciteturn0file0L189-L192

---

# 14. Security Requirements

Must implement:

- API keys only through env vars/config secret references
- no keys in baseline files
- no keys in logs
- sanitized exceptions
- optional raw-output suppression
- no default telemetry
- dependency auditing
- secure GitHub Action permissions
- safe prompt templating

Document:

```text
What data leaves my machine?
Where are outputs stored?
Does PromptDrift have telemetry?
How are CI secrets handled?
```

The answer should be clear directly in the README.

---

# 15. Error Handling

Never show raw stack traces by default.

Bad:

```text
Traceback ...
```

Preferred:

```text
Error: OPENAI_API_KEY is not set.

Set it with:

export OPENAI_API_KEY="..."
```

For debugging:

```bash
promptdrift test --verbose
```

Use distinct exception types:

```text
ConfigError
ProviderError
EvaluationError
BaselineError
TemplateError
```

---

# 16. Performance Requirements

The CLI should avoid unnecessary overhead.

Requirements:

- do not load heavyweight embedding models unless semantic evaluation is requested
- allow test concurrency where provider rate limits permit
- provide deterministic ordering in reports
- cache safe/reusable local evaluation artifacts
- avoid unnecessary duplicate model calls
- support selective test execution

Do not promise “zero config” if a model download or provider key is required. The original plan identified local embedding model download as a friction point. fileciteturn0file0L217-L220

---

# 17. Testing Strategy

The project must have multiple levels of tests.

## Unit

Cover:

- YAML parsing
- template rendering
- assertion logic
- JSON schema evaluation
- regression classification
- baseline serialization
- CLI option parsing

## Integration

Cover:

- provider adapter with mocked network
- full test execution pipeline
- baseline generation
- diff
- JSON output
- Action input parsing

## Golden/snapshot tests

Use stable fixtures for:

- CLI output
- JSON reports
- PR comment formatting
- HTML reports

## Optional live tests

Provide:

```bash
pytest -m live
```

Live tests must be opt-in.

---

# 18. Packaging

Use modern Python packaging.

Requirements:

- `pyproject.toml`
- Python 3.11+ unless a dependency forces a different minimum
- buildable wheel
- source distribution
- `pip install promptdrift`
- `uvx promptdrift`

Expose CLI entry point:

```text
promptdrift = promptdrift.cli:main
```

Publish to PyPI.

Ensure import and command startup are fast.

---

# 19. README/Product Marketing Requirements

README is not an afterthought.

Top section should immediately communicate:

```text
PromptDrift

CI regression testing for LLM prompts.

Catch AI behavior regressions before they reach production.
```

Then show:

```text
prompt change
    ↓
PromptDrift test
    ↓
21 passed
2 warnings
1 failed
    ↓
GitHub PR blocked
```

The README should contain a realistic before/after PR example.

Do not lead with architecture.

Lead with the user problem and the result.

The research indicates that strong developer-tool repos benefit from a clear one-line description, quick demo, strong documentation, issue/contribution templates, and a polished repository presentation. fileciteturn0file0L135-L143

---

# 20. Open-Source Repository Quality

Include:

```text
LICENSE
README.md
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
CHANGELOG.md
```

Add:

- issue forms/templates
- pull request template
- labels such as `good first issue`, `help wanted`
- release automation
- CI status badge
- package version badge
- documentation links

GitHub issue templates/forms should make contributions easy and specific.

---

# 21. Versioning

Use Semantic Versioning.

Initial:

```text
0.1.0
```

until the core API and config format are reasonably stable.

Configuration schema must include:

```yaml
version: 1
```

Never make breaking config changes silently.

---

# 22. Observability of PromptDrift Itself

The project must not depend on telemetry.

However, add local diagnostics where useful:

```bash
promptdrift doctor
promptdrift --verbose
```

For CI, produce:

- test counts
- pass/warn/fail counts
- runtime
- provider/model
- evaluator summary

Do not send those metrics anywhere by default.

---

# 23. Developer Experience Goals

A new developer should be able to do:

```bash
pip install promptdrift
promptdrift init
promptdrift test
```

with minimal explanation.

A repository maintainer should be able to add:

```yaml
- uses: promptdrift/action@v1
```

and have CI protection.

A developer reviewing a failing PR should understand:

1. which test failed
2. what expected behavior was
3. what changed
4. why PromptDrift considers it a regression
5. how to reproduce locally

This is the most important UX requirement.

---

# 24. Example End-to-End Scenario

Prompt:

```text
You are a customer support assistant.

Answer customer questions using the policy below:

{{ policy }}

Customer:
{{ question }}

Never promise a refund unless policy explicitly allows it.
```

Test:

```yaml
- id: refund_request
  prompt: prompts/support.txt

  variables:
    policy: |
      Refunds are available within 30 days.
    question: |
      Can I get a refund for my order?

  assertions:
    - type: contains
      value: "30 days"

    - type: not_contains
      value: "guaranteed"

    - type: max_length
      value: 600
```

Developer changes the prompt and accidentally removes the policy.

PromptDrift should produce:

```text
❌ FAIL refund_request

Assertion:
contains

Expected:
30 days

Actual:
Yes, you may be eligible for a refund.

Reason:
Required policy constraint no longer appears in the output.
```

GitHub Action:

```text
❌ PromptDrift regression detected

1 failed
0 warnings
0 passed

PR check failed.
```

This is the canonical demo use case.

---

# 25. Growth-Oriented Product Decisions

Optimize for genuine adoption, not artificial star/download inflation.

The project should be easy to:

- discover
- install
- understand
- demo
- run locally
- add to GitHub Actions
- contribute to
- fork
- use in public examples

Avoid fake stars, star exchanges, spam, misleading download claims, or automated engagement.

The strongest growth loop is:

```text
Interesting problem
        ↓
Excellent README/demo
        ↓
Developer tries CLI
        ↓
Developer adds Action
        ↓
PromptDrift appears in PR
        ↓
Team sees value
        ↓
Repository/Action gets shared
        ↓
More users/contributors
```

---

# 26. Launch-Readiness Requirements

Before calling the project “release ready”, verify:

## Product

- [ ] CLI works from a clean environment
- [ ] `pip install promptdrift` works
- [ ] `uvx promptdrift` works
- [ ] OpenAI provider works
- [ ] Ollama provider works
- [ ] YAML configuration works
- [ ] baseline generation works
- [ ] diff works
- [ ] deterministic assertions work
- [ ] regression classification works
- [ ] JSON output works
- [ ] GitHub Action works
- [ ] PR summary works
- [ ] doctor works

## Quality

- [ ] unit tests
- [ ] integration tests
- [ ] CLI snapshot tests
- [ ] security review
- [ ] dependency audit
- [ ] no secret leakage
- [ ] clean error messages

## Documentation

- [ ] README complete
- [ ] getting-started guide
- [ ] configuration reference
- [ ] provider docs
- [ ] GitHub Action docs
- [ ] baseline docs
- [ ] architecture docs
- [ ] FAQ

## Repository

- [ ] LICENSE
- [ ] CONTRIBUTING
- [ ] CODE_OF_CONDUCT
- [ ] SECURITY
- [ ] CHANGELOG
- [ ] issue templates
- [ ] PR template
- [ ] CI workflow
- [ ] release workflow

---

# 27. Acceptance Criteria

Claude should consider the initial implementation successful when all of the following are true.

### Installation

```bash
pip install promptdrift
promptdrift version
```

works.

### Local workflow

A developer can:

```bash
promptdrift init
promptdrift test
promptdrift baseline
promptdrift diff
```

without manually modifying internal application code.

### Regression workflow

A prompt change that breaks a required assertion causes:

```text
exit code 1
```

and a clear explanation.

### GitHub workflow

A pull request can automatically run PromptDrift and produce a readable summary.

### Determinism

The same mocked inputs produce the same evaluation results.

### Security

No API secret appears in:

- logs
- baseline
- reports
- PR comments
- exceptions

### Architecture

Provider, evaluator, baseline, reporting, and GitHub integrations are modular enough that new providers/evaluators can be added without rewriting the core engine.

---

# 28. Implementation Instructions to Claude

Claude should follow these rules while coding this project.

1. Start by inspecting the repository and current state.
2. Build the core domain models and interfaces first.
3. Implement the deterministic evaluation engine before advanced semantic evaluation.
4. Keep the baseline file canonical and Git-friendly.
5. Keep provider code isolated behind adapters.
6. Do not add a web dashboard.
7. Do not add telemetry.
8. Do not create unnecessary infrastructure.
9. Keep dependencies minimal.
10. Add tests alongside each major component.
11. Keep CLI behavior stable and documented.
12. Ensure error messages are actionable.
13. Prefer simple implementations over abstractions that are not currently needed.
14. Do not invent product requirements that are not in this document.
15. When a design choice is ambiguous, choose the smallest implementation consistent with this specification.
16. Before declaring a feature complete, add tests for its success and failure paths.
17. Keep the repository in a runnable state after every meaningful implementation step.

---

# 29. Suggested Initial Dependency Set

Prefer a small dependency footprint.

Likely dependencies:

```text
typer
rich
pyyaml
pydantic
httpx
jinja2
jsonschema
```

Provider integration may use:

```text
litellm
```

if it reduces maintenance and does not compromise the abstraction.

Optional dependencies should be separated where possible:

```text
semantic evaluation
html reporting
live provider integrations
```

Do not require heavy ML dependencies for the basic CLI.

---

# 30. Future Extensions

These are explicitly outside the initial scope but should not be architecturally blocked.

Potential future features:

- OpenTelemetry ingestion
- VS Code extension
- conversation/multi-turn testing
- advanced RAG evaluation
- test generation
- agent regression testing
- hosted dashboard
- team collaboration
- public benchmark dataset
- plugin ecosystem
- optional hosted CI service

The original plan identified OpenTelemetry, a VS Code extension, community drift reporting, structured-output drift, and multi-turn drift as later opportunities. fileciteturn0file0L225-L230

---

# 31. Final Product Definition

Do not lose the core idea.

PromptDrift is not:

> “A platform for all LLM evaluations.”

PromptDrift is:

> **A GitHub-native regression testing tool that tells developers when a prompt change changes AI behavior in a way that matters.**

The ideal first impression is:

```text
I changed my prompt.
PromptDrift ran 40 tests.
It found 2 regressions.
It explained exactly what broke.
My PR was blocked before production.
```

That is the product.

---

# 32. Reference Research

The design should remain informed by the current LLM tooling ecosystem without becoming a clone of broader platforms.

Useful adjacent projects/references:

- Promptfoo — https://github.com/promptfoo/promptfoo
- Langfuse — https://github.com/langfuse/langfuse
- Ragas — https://github.com/vibrantlabsai/ragas
- Arize Phoenix — https://github.com/Arize-ai/phoenix
- Helicone — https://github.com/Helicone/helicone
- ContextCheck — https://github.com/Addepto/contextcheck
- GitHub Actions LLM testing examples — https://github.com/marketplace/actions/test-llm-outputs

Research conclusion:

PromptDrift should differentiate through a narrower CI-native regression workflow, deterministic behavioral contracts, Git-friendly baselines, clear PR feedback, and minimal setup rather than competing feature-for-feature with full LLMOps platforms.

---

# 33. Final Instruction

**Build PromptDrift according to this specification.**

Do not create a week-by-week roadmap.

Do not start with a dashboard.

Do not over-engineer.

Prioritize:

```text
CLI
→ YAML tests
→ provider abstraction
→ deterministic assertions
→ baseline
→ regression engine
→ GitHub Action
→ PR feedback
→ excellent docs/tests
→ optional semantic evaluation
```

The end result should be a production-quality open-source developer tool that is genuinely useful to developers working with LLM applications and is polished enough to become a strong GitHub portfolio project.
