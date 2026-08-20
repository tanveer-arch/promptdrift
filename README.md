# PromptDrift

## CI regression testing for LLM prompts.

**Catch AI behavior regressions before they reach production.** PromptDrift runs declarative behavioral contracts against your prompts, compares results with a Git-friendly baseline, and produces a PR-ready result.

```bash
pip install promptdrift
promptdrift init
promptdrift test
```

```text
❌ PromptDrift regression detected

support_json
Missing required property: escalation_required

PR check failed.
```

Prompt output changing is not automatically a failure. PromptDrift fails when a declared contract breaks: invalid structured output, missing policy text, forbidden language, limits, latency, or cost.

## Minimal configuration

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
      question: Can I get a refund?
    assertions:
      - type: contains
        value: 30 days
      - type: not_contains
        value: guaranteed
```

```bash
promptdrift baseline   # commit promptdrift.baseline.json
promptdrift diff       # fail on broken contracts
```

## GitHub Actions

```yaml
- uses: promptdrift/action@v1
  with:
    config: promptdrift.yaml
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Use `pull_request`, not `pull_request_target`, when checking untrusted fork code. Do not provide secrets to workflows running forked pull requests.

## Commands

`init`, `test`, `baseline`, `diff`, `report`, `doctor`, and `version` all support `--help`; execution commands support `--json` and `--verbose`. Optional semantic and judge evaluators are deliberately not accepted in 0.1.0: deterministic contracts remain the release's source of truth.

Exit codes: `0` success, `1` contract/regression failure, `2` configuration or usage error, `3` provider/runtime error.

## Privacy and security

PromptDrift has no telemetry, accounts, hosted database, or dashboard. Prompt data only goes to the provider you configure. API keys are read from environment variables; baselines contain hashes and metrics, not API keys or raw outputs.

See [documentation](docs/getting-started.md), [contributing](CONTRIBUTING.md), and [security policy](SECURITY.md).
