# PromptDrift — Product & Implementation Plan

## Mission

Evolve PromptDrift from a YAML-first LLM regression test runner into a **Git-native AI behavior change detector** that gives developers useful regression coverage with minimal manual setup.

Core product promise:

> **Change a prompt. PromptDrift automatically shows what changed in AI behavior, what broke, what improved, and whether the change is safe to merge.**

The tool must remain local-first, privacy-first, CLI-first, CI-friendly, and easy to adopt.

---

# 1. Product Principles

Build around these principles:

1. **Zero-to-value quickly** — a developer should get a useful result without first authoring dozens of YAML tests.
2. **Git-native** — PromptDrift understands changed prompts, baselines, branches, and pull requests.
3. **Evidence over a magic score** — do not create one opaque “AI quality score.” Show regressions, improvements, unchanged cases, latency, tokens, cost, and evidence.
4. **Real behavior over cosmetic output diffs** — wording changes are not automatically regressions.
5. **Manual control remains available** — advanced users can still define explicit contracts and tests.
6. **Privacy by default** — no mandatory hosted service, telemetry, account, or remote storage.
7. **Safe automation** — generated tests and suggested contracts are candidates until explicitly accepted.
8. **Backward compatibility** — existing `promptdrift.yaml`, baselines, CLI commands, reports, and GitHub Action should continue working.

---

# 2. Current Architecture — Preserve and Extend

The existing repository already provides:

- Python CLI via Typer
- `promptdrift init`, `test`, `baseline`, `diff`, `report`, `doctor`, `version`
- OpenAI, Ollama, and Mock providers
- deterministic assertions
- baseline comparison
- local SQLite run history
- JSON/HTML/terminal reports
- GitHub Action and PR comments
- local/privacy-first behavior

Current project/package facts:

- Repository: `tanveer-arch/promptdrift`
- Package: `promptdrift-ci`
- Current Python requirement: `>=3.11`
- Main package path: `src/promptdrift`
- Tests live under `tests/`

Do **not** rewrite the project into a different framework. Extend the current provider, evaluator, baseline, report, history, and CLI layers.

The current README is YAML-first and describes explicit contracts and a canonical baseline. Preserve that advanced workflow while adding an easier automatic workflow.

---

# 3. New Product Model

Move from:

```text
promptdrift.yaml
        ↓
manual tests
        ↓
manual assertions
        ↓
baseline
        ↓
CI
```

toward:

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

The existing explicit YAML suite becomes the **advanced mode**, not the only mode.

---

# 4. Core New Features

## 4.1 `promptdrift init` — zero-config project setup

Upgrade `init` so it detects the project context and offers an appropriate setup instead of only writing a static example.

Discovery should inspect, safely and locally:

- Git repository presence
- common prompt directories/files
- Python/Node project indicators
- common OpenAI/Ollama usage patterns where detectable without executing application code
- existing PromptDrift configuration
- existing test/example data
- GitHub workflow directory

Example UX:

```text
$ promptdrift init

✓ Git repository detected
✓ Prompt files detected: prompts/, system.txt
✓ OpenAI usage detected in src/ai.py
✓ No existing PromptDrift suite found

Choose setup:
  1. Learn from examples / captured cases
  2. Start with explicit YAML tests
  3. Offline demo

Selection:
```

Do not require secrets during initialization.

Add `--yes` / non-interactive behavior for CI and scripts.

---

# 5. Real-Interaction Capture

## 5.1 Goal

Let developers build a regression suite from real application interactions instead of manually writing every test.

Provide an opt-in local capture path.

Recommended initial interfaces:

```bash
promptdrift capture
```

and, where practical:

```bash
promptdrift proxy
```

Do not implement both as disconnected systems. Build one reusable capture/session layer and expose whichever interfaces are feasible.

## 5.2 Capture data model

Create a privacy-aware interaction record containing fields such as:

- interaction ID
- timestamp
- provider
- model
- prompt/system prompt reference or hash
- user input
- relevant variables/context metadata
- output
- latency
- input tokens
- output tokens
- estimated cost
- optional tags
- source (`capture`, `manual`, `import`, `generated`)

Raw prompts/outputs must remain local and must not be written to Git baselines by default.

Use redaction hooks where practical.

## 5.3 Storage

Extend the existing local SQLite history instead of creating a second unrelated database.

Add versioned schema migrations.

Example conceptual tables:

```text
runs
interactions
scenarios
scenario_versions
evaluations
contracts
```

Keep Git-tracked artifacts separate from local history.

---

# 6. Scenario Discovery / `learn`

Introduce:

```bash
promptdrift learn
```

Purpose:

Take captured/manual interactions and turn them into **candidate regression scenarios**.

The output should be deterministic where possible and transparent when AI assistance is used.

Example:

```text
✓ 127 interactions loaded
✓ 42 candidate scenarios discovered
✓ 16 high-value regression candidates

Suggested categories:
  refund             7
  cancellation       4
  order-status       3
  escalation         2

Review candidates:
  promptdrift scenarios

Accept all reviewed candidates:
  promptdrift promote ...
```

## 6.1 Candidate generation

Start with deterministic grouping before adding an LLM-powered clustering layer.

Potential grouping signals:

- normalized input similarity
- prompt/template identity
- variables
- tags
- output schema
- known assertion outcomes

Later, optionally support embedding/semantic clustering behind an optional dependency.

Never silently upload captured content to a third party.

## 6.2 Scenario artifact

Introduce a stable versioned file, for example:

```text
.promptdrift/scenarios.json
```

or

```text
promptdrift.scenarios.json
```

Prefer a machine-friendly JSON format for generated data and keep human-authored YAML supported.

Each scenario should contain:

```json
{
  "id": "refund_request_001",
  "input": "Can I get a refund for my order?",
  "variables": {
    "policy": "Refunds are available within 30 days."
  },
  "source": "captured",
  "status": "candidate"
}
```

Avoid storing raw production data unless the developer explicitly promotes it.

---

# 7. Automatic Contract Suggestions

Introduce:

```bash
promptdrift suggest
```

Purpose:

Detect repeated behavioral invariants and suggest assertions/contracts instead of requiring users to author them all manually.

Example:

```text
Suggested behavioral contracts for refund_request:

✓ Must mention the applicable refund window
✓ Must not promise a guaranteed refund
✓ Response should remain under 600 characters

Accept:
  promptdrift promote-contract ...
```

## 7.1 Deterministic suggestions first

Derive obvious contracts from:

- JSON schema already present
- stable output fields
- repeated forbidden phrases
- repeated required patterns
- existing application tests
- response length distributions
- explicit developer annotations

## 7.2 Optional LLM judge later

Add an optional evaluator abstraction for semantic judging.

Example:

```yaml
evaluators:
  - type: llm_judge
    rubric: "Answer according to the refund policy and do not invent guarantees."
```

Do not make LLM judging mandatory for the basic product.

Never silently turn subjective judge scores into hard CI failures without configured thresholds.

---

# 8. Replace Raw Output Diff With Change Classification

The current baseline engine correctly avoids treating every output hash change as a regression. Preserve this behavior.

Extend it into a richer classification system:

```text
REGRESSED
IMPROVED
UNCHANGED
CHANGED_BUT_VALID
NEW
MISSING
```

The exact categories may be refined during implementation, but the meaning must be explicit and deterministic.

For each scenario compare baseline vs current on:

- behavioral assertions
- semantic evaluator results when enabled
- output hash/change
- latency
- input tokens
- output tokens
- estimated cost

---

# 9. Impact Radius

Create a first-class concept called **Impact Radius**.

The report should answer:

> How much of the tested behavior changed because of this prompt change?

Example:

```text
Impact Radius

43 scenarios evaluated
5 improved
35 unchanged
3 regressed

Affected scenarios: 8 / 43 (18.6%)
```

Also group affected scenarios by:

- tag/category
- prompt
- contract type
- severity

Example:

```text
Refunds          5 affected
Cancellation     2 affected
Escalation       1 affected
```

Do not imply that impact radius is a universal business-risk score. It is an observed/tested coverage metric.

---

# 10. Before / After Behavior Report

Add a new high-level report designed around developer questions.

The report should prioritize:

```text
WHAT CHANGED?
WHAT BROKE?
WHAT IMPROVED?
WHAT DID NOT CHANGE?
WHAT DOES IT COST?
```

Example:

```text
PromptDrift

Behavior
────────────────────────
43 scenarios
  3 regressed
  5 improved
 35 unchanged

Impact radius: 18.6%

Performance
────────────────────────
Latency      +7.2%
Input tokens +4.1%
Output tokens +6.8%
Cost         +11.3%

Regressions
────────────────────────
✗ refund_request
  Required policy condition failed

✗ cancellation
  JSON schema violated

✗ escalation
  Required escalation behavior missing

Changed but valid
────────────────────────
17 responses changed wording while all contracts passed.
```

Do not output an opaque single quality score.

---

# 11. `promptdrift check`

Introduce:

```bash
promptdrift check
```

This becomes the preferred high-level command for CI and local usage.

Behavior:

1. Determine baseline reference.
2. Determine changed prompt files relative to Git base where possible.
3. Identify affected scenarios.
4. Run only the relevant suite when safely possible.
5. Compare baseline vs current.
6. Produce human-readable impact report.
7. Return proper exit code based on configured policy.

Support:

```bash
promptdrift check --base origin/main
promptdrift check --config promptdrift.yaml
promptdrift check --json
```

Do not remove `test` or `diff`; keep them as lower-level compatibility commands.

---

# 12. Git-Aware Scenario Selection

Implement a Git integration layer that can:

- detect current branch
- detect merge base/base ref when available
- inspect changed files
- identify changed prompt files/config/scenario artifacts
- map changed prompts to affected scenarios

Start with a transparent file-to-scenario relationship.

Example:

```text
prompts/support.txt
        ↓
refund_request
cancellation
late_delivery
```

Then `check` can avoid executing unrelated scenarios when safe.

If no mapping is known, fall back to the full suite.

Never silently skip coverage because mapping failed.

---

# 13. Baseline Redesign — Keep Baseline, Reduce Manual Maintenance

Do NOT remove the baseline system.

Instead, introduce baseline metadata:

```json
{
  "schema_version": 2,
  "created_at": "...",
  "prompt_revision": "...",
  "provider": "openai",
  "model": "...",
  "scenarios": {}
}
```

Store:

- output hash
- selected metrics
- assertion outcomes
- evaluator scores when enabled
- scenario metadata

Do not store raw output by default.

## Baseline policy

Distinguish:

### Intentional contract change

Developer changes the expected behavior.

Then they explicitly approve/promote the change.

### Accidental behavior change

Prompt changed but contract unexpectedly breaks.

PromptDrift should flag it.

This distinction is essential to preventing stale baselines from becoming meaningless.

Provide a guided approval command such as:

```bash
promptdrift accept
```

with options to accept:

- all reviewed changes
- selected scenarios
- only intentional contract changes

Require explicit confirmation for baseline replacement.

---

# 14. Make Policy Changes Easy

Address the key usability concern: business requirements change.

When a contract fails because the business changed intentionally, show:

```text
Contract appears intentionally changed.

Baseline:
Refunds allowed within 30 days.

Current configured behavior:
Refunds allowed within 60 days.

Actions:
  [edit contract]
  [accept as new baseline]
  [keep old requirement]
```

Do not automatically rewrite contracts from model output.

The tool can suggest the update; the developer must approve it.

---

# 15. Production-to-Regression Loop

This is the long-term differentiator.

Implement the loop:

```text
real interaction
      ↓
interesting behavior detected
      ↓
candidate scenario
      ↓
developer review
      ↓
promoted regression test
      ↓
Git-tracked suite
```

Add a command such as:

```bash
promptdrift promote <scenario-id>
```

This converts a candidate into a committed regression case.

Potential reasons to suggest promotion:

- repeated scenario
- previous failure
- high-severity contract
- significant behavior variance
- manually tagged interaction

Keep the decision human-controlled.

---

# 16. Optional Semantic Evaluation Layer

Create a clean evaluator interface separate from deterministic assertions.

Example interface concept:

```python
class Evaluator(Protocol):
    def evaluate(self, case: TestCase, response: ModelResponse) -> EvaluationResult:
        ...
```

Implement:

1. Existing deterministic assertions.
2. Embedding similarity evaluator as optional.
3. LLM-as-judge evaluator as optional.

The product should remain fully usable without an evaluator API key.

Semantic evaluations must expose:

- evaluator name
- rubric
- score
- pass threshold
- model used for judging
- confidence/metadata when applicable

Avoid presenting judge outputs as objective truth.

---

# 17. Multi-Provider Comparison

Add a later extension to run the same scenario suite through multiple models/providers.

Example:

```bash
promptdrift compare --models gpt-4.1-mini,ollama-local
```

Report:

```text
Scenario: refund_request

Model                 Pass   Latency   Cost
------------------------------------------------
gpt-4.1-mini          98%    0.8s      $0.003
ollama-local          94%    1.4s      $0
```

Do not make this the first-run experience. It is an advanced feature.

---

# 18. GitHub PR Experience

The PR comment is the flagship output for teams using CI.

Update the existing GitHub Action/reporting flow rather than replacing it.

The comment should be compact at the top and expandable/detail-oriented underneath.

Example:

```text
## PromptDrift

⚠ 3 behavioral regressions detected

| Metric | Baseline | Current | Change |
|---|---:|---:|---:|
| Scenarios | 43 | 43 | — |
| Regressed | 0 | 3 | +3 |
| Improved | 0 | 5 | +5 |
| Latency | 0.91s | 0.98s | +7.2% |
| Cost | $0.031 | $0.035 | +11.3% |

### Regressions

- `refund_request` — required policy behavior failed
- `cancellation` — JSON schema violation
- `escalation` — escalation contract failed

### Changed but valid

17 scenarios changed wording but still satisfy all contracts.

[View full PromptDrift report]
```

The current action already supports Step Summary, JSON artifact upload, and optional PR comments. Preserve its fork/secret safety model. Update it to consume the richer report structure. 

---

# 19. CI Behavior

Default safe behavior:

- fail on configured `severity: fail` contract regressions
- warn on non-blocking warnings
- never fail merely because output wording changed
- expose report before failing the job
- preserve current fork-safe behavior

Allow configuration:

```yaml
policy:
  fail_on:
    - regression
    - critical_contract
  warn_on:
    - cost_increase
    - latency_increase
```

Do not invent business-risk thresholds automatically.

---

# 20. CLI Design

Recommended final command set:

```text
promptdrift init
promptdrift capture
promptdrift learn
promptdrift suggest
promptdrift scenarios
promptdrift promote
promptdrift test
promptdrift baseline
promptdrift diff
promptdrift check
promptdrift report
promptdrift doctor
promptdrift version
```

Every command that is useful to automation should support:

```text
--json
```

Use consistent exit codes:

```text
0 = pass / success
1 = behavioral regression according to policy
2 = config / usage error
3 = provider / runtime error
```

Do not break existing meanings.

---

# 21. Configuration Design

Keep `promptdrift.yaml` backward compatible.

Add optional sections rather than forcing migration:

```yaml
version: 2

project:
  name: support-bot

provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY

sources:
  prompts:
    - prompts/**

scenarios:
  file: .promptdrift/scenarios.json

evaluation:
  semantic:
    enabled: false

policy:
  fail_on:
    - regression
```

Do not require users to add every optional field.

---

# 22. Data Privacy

This feature set can easily become privacy-sensitive. Treat this as a first-class engineering requirement.

Requirements:

- capture disabled unless explicitly enabled
- no telemetry
- no cloud account required
- raw captured data local by default
- no raw outputs in baseline files by default
- redact likely secrets where practical
- never place API keys in generated config
- clear documentation for production capture
- explicit command to export/delete local captured data

Add:

```bash
promptdrift doctor --privacy
promptdrift purge
```

if consistent with the existing storage architecture.

---

# 23. Testing Strategy

Build tests before declaring the new workflow complete.

## Unit tests

Add tests for:

- Git diff parsing
- changed prompt detection
- scenario grouping
- candidate generation
- candidate promotion
- contract suggestion
- baseline schema migration
- before/after classification
- impact-radius calculation
- metric deltas
- evaluator interface
- report rendering
- exit policy

## Integration tests

Test:

```text
init
 → capture fixture
 → learn
 → promote
 → baseline
 → modify prompt
 → check
 → report
```

Use deterministic Mock provider fixtures for normal tests.

## Regression tests

Explicitly test:

1. wording-only change → not a regression when contracts remain valid
2. required content disappearance → regression
3. forbidden content appearance → regression
4. JSON structure break → regression
5. performance threshold violation → correct warning/failure
6. intentional contract update → baseline can be safely accepted
7. new scenario → handled without corrupting baseline
8. deleted scenario → handled explicitly
9. missing baseline → predictable behavior
10. Git base unavailable → safe full-suite fallback
11. captured raw data does not leak into Git baseline by default
12. fork PR cannot write secrets/comments unsafely

## Optional live tests

Keep live provider tests marked `live` and excluded from default CI unless explicitly enabled.

---

# 24. Architecture Changes

Target module structure:

```text
src/promptdrift/
├── cli.py
├── config.py
├── templates.py
├── models.py
├── providers/
├── assertions/
├── evaluators/
├── baseline.py
├── regression.py
├── reports/
│   ├── terminal.py
│   ├── json.py
│   ├── html.py
│   └── github.py
├── history/
├── capture/
├── scenarios/
├── git.py
├── impact.py
├── policy.py
└── storage/
```

Names can differ if the existing codebase already has cleaner equivalents. Do not duplicate concepts just to match this diagram.

Prefer small interfaces:

```text
Provider
Evaluator
ScenarioSource
ScenarioGenerator
BaselineStore
HistoryStore
ReportFormatter
GitContext
PolicyEngine
```

---

# 25. Migration / Backward Compatibility

Existing users must be able to continue running:

```bash
promptdrift test
promptdrift baseline
promptdrift diff
promptdrift report
```

Existing YAML should load without modification whenever possible.

Existing baseline files should either:

- remain valid, or
- migrate automatically and safely with an explicit schema version.

Do not silently overwrite user data.

---

# 26. Documentation Rewrite

Rewrite the README around the **developer problem**, not around implementation details.

New opening should communicate:

```text
Your prompt changed.

Did your AI behavior change?

PromptDrift answers that in CI.
```

Show a complete 3-minute workflow first.

Recommended README structure:

1. Problem
2. Demo before/after PR
3. 3-minute quick start
4. Zero-config discovery
5. Capture + learn workflow
6. GitHub Action
7. Advanced YAML contracts
8. Supported providers
9. Privacy
10. Architecture
11. Contributing

Position PromptDrift as:

> **Git-native regression protection for AI behavior.**

Avoid positioning it as a general-purpose “LLM evaluation platform.”

---

# 27. Packaging / Naming Cleanup

The GitHub project is `promptdrift` while the package is currently `promptdrift-ci`.

Do not immediately break the PyPI name, but investigate whether the package/repository naming can be made clearer.

Ensure CLI docs, PyPI metadata, README badges, and GitHub Action references are consistent.

Do not claim a package rename is complete until the package actually exists and installs successfully.

---

# 28. Performance

The tool must remain lightweight for small projects.

Requirements:

- deterministic local operations should be fast
- only affected scenarios should run when safely identifiable
- parallel execution should be optional/configurable
- retries must be bounded
- network/API calls should have timeouts
- capture storage should be efficient
- HTML/JSON reports should not load entire production datasets unnecessarily

Add:

```bash
promptdrift check --parallel 4
```

only if implementation can preserve provider safety/rate-limit behavior.

---

# 29. Failure Handling

Design for real-world failures:

- provider unavailable
- rate limit
- malformed provider output
- Git unavailable
- no baseline
- stale baseline
- deleted scenario
- invalid generated scenario
- capture storage failure
- judge evaluator unavailable

The report should distinguish:

```text
behavioral regression
vs
infrastructure/provider failure
```

Do not label an API outage as an AI regression.

---

# 30. What NOT to Build

Do not turn PromptDrift into:

- a hosted observability platform
- a generic chatbot playground
- a giant evaluator marketplace
- an opaque AI quality score
- an automatic contract rewrite engine
- a production data warehouse
- an unrestricted autonomous test generator

Those dilute the main product identity.

---

# 31. Definition of Done

The redesign is complete only when a new developer can do something close to:

```bash
pip install promptdrift-ci
promptdrift init
promptdrift capture
promptdrift learn
promptdrift promote
promptdrift baseline
```

then make a prompt change and run:

```bash
promptdrift check
```

and receive:

```text
PromptDrift

Behavior changed in 8 / 43 scenarios.

✓ 5 improved
⚪ 35 unchanged
✗ 3 regressed

Impact radius: 18.6%

Latency: +7.2%
Cost:    +11.3%

Regressions:
  ✗ refund_request
  ✗ cancellation
  ✗ escalation

Changed but valid:
  17 scenarios
```

Then the same report must appear in GitHub CI/PR comments without requiring a hosted PromptDrift account.

A developer who prefers explicit tests must still be able to use the existing YAML workflow.

---

# 32. Implementation Order

Implement in dependency order, not as a calendar/week plan:

```text
1. Refactor/extend domain models and storage interfaces
        ↓
2. Git context + changed-file detection
        ↓
3. Scenario model + scenario store
        ↓
4. Capture ingestion layer
        ↓
5. Scenario discovery (`learn`)
        ↓
6. Promotion workflow
        ↓
7. Contract suggestion engine
        ↓
8. Baseline schema v2 + migration
        ↓
9. Before/after classification
        ↓
10. Impact-radius engine
        ↓
11. New `check` orchestration
        ↓
12. Rich CLI/JSON/HTML reports
        ↓
13. GitHub PR report integration
        ↓
14. Semantic evaluator interface + optional implementations
        ↓
15. Multi-provider comparison
        ↓
16. Documentation / examples / migration guide
        ↓
17. Full test suite + packaging validation
```

Do not skip foundational interfaces just to make the CLI appear complete.

---

# 33. Claude Execution Instructions

You are implementing this plan in the existing PromptDrift repository.

Before coding:

1. Inspect the complete repository.
2. Read the existing README, docs, CLI, models, config, baseline, regression, storage/history, reports, GitHub Action, and tests.
3. Map the current architecture.
4. Identify where each new capability belongs.
5. Do not rewrite working functionality unnecessarily.

During implementation:

- preserve public APIs where practical
- preserve old commands
- use typed Python
- add tests alongside new behavior
- use small composable modules
- keep optional dependencies optional
- keep live-provider calls out of default tests
- make all new generated artifacts versioned
- do not store secrets/raw production data in Git by default
- do not make LLM judgments mandatory
- do not create an opaque quality score
- do not silently modify baselines/contracts

For any ambiguous design decision, prefer:

```text
simple
local
Git-friendly
explainable
backward-compatible
```

over:

```text
complex
hosted
opaque
automagic
```

Before finishing, run:

```bash
pytest
ruff check .
```

and the relevant packaging/build checks.

Also manually exercise the new happy path using the deterministic mock provider.

Finally provide:

- architecture changes
- files changed
- new commands
- new configuration/artifacts
- migration behavior
- tests added
- commands/tests executed
- remaining limitations

Do not claim a feature works unless it was actually implemented and tested.

---

# 34. Final Product Positioning

The final product should feel like this:

```text
                    PROMPTDRIFT
                         │
             “What changed in my AI?”
                         │
          ┌──────────────┴──────────────┐
          │                             │
    Real interactions              Explicit tests
          │                             │
          └──────────────┬──────────────┘
                         ↓
                 Scenario Library
                         ↓
                    Baseline
                         ↓
                   Git Change
                         ↓
                Replay + Evaluate
                         ↓
                Impact Analysis
                         ↓
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
       Improved       Unchanged      Regressed
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                     GitHub PR
```

The differentiator is not “more LLM metrics.”

The differentiator is **making AI behavior regression testing feel like a normal Git workflow, while automatically turning real application behavior into reusable regression coverage.**
