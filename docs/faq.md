# FAQ

## General

### What is PromptDrift?

PromptDrift is a CLI tool and GitHub Action for regression-testing LLM prompts. It lets you define behavioral contracts (assertions) for your prompts and automatically checks them in CI — so you catch unintended behavior changes before they reach production.

### How is PromptDrift different from a regular diff?

A `git diff` shows you what changed in the prompt **text**. PromptDrift tells you whether the AI **behavior** changed in a way that matters. Rewording a prompt is fine — silently dropping a required field from the response is not.

### Does PromptDrift send telemetry?

No. PromptDrift has no analytics, tracking, hosted service, or phone-home behavior. Your prompt content goes only to the LLM provider you configure.

### Is PromptDrift a hosted service?

No. PromptDrift runs entirely locally or in your own CI pipeline. There are no accounts, dashboards, or remote databases.

## Behavior

### Does an output change fail my build?

No. A failure requires a **violated assertion** (e.g., required text missing, invalid JSON, schema mismatch). If the output changed but all assertions still pass, PromptDrift adds a diagnostic note but keeps the status as PASS.

### Can I get warnings without blocking CI?

Yes. Set `severity: warn` on any assertion:

```yaml
- type: not_contains
  value: "guaranteed"
  severity: warn
```

Warnings appear in reports but don't set a non-zero exit code.

### What happens when I add a new test that has no baseline?

The test runs normally against assertions. If it passes, the status is set to WARN with a note saying "Test has no baseline." Run `promptdrift baseline --force` to update the baseline.

### Can I use PromptDrift without a baseline?

Yes. Baselines are optional. Without one, `promptdrift test` evaluates all assertions and exits with code 1 if any fail. Baselines add regression detection on top.

## Privacy and Security

### Where does prompt data go?

Only to the LLM provider you configure. The `mock` provider is entirely local — no network calls at all.

### Are API keys stored in config?

No. API keys are read exclusively from environment variables. The config file only stores the **name** of the variable (e.g., `api_key_env: OPENAI_API_KEY`), never the value.

### What's in the baseline file?

Output hashes (SHA-256), assertion results, and performance metrics. Raw outputs and prompt text are **not** stored in the baseline. It's safe to commit to public repositories.

### Is local history safe?

The SQLite history at `~/.promptdrift/promptdrift.db` suppresses raw prompts and outputs by default. Set `baseline.store_raw_output: true` to keep them — useful for debugging but only store locally.

## CI and GitHub

### Can I use PromptDrift with fork PRs?

Yes, but with care. Use the `pull_request` event (not `pull_request_target`) and either:
- Use the `mock` provider (no API key needed)
- Skip tests that require a real provider

Never expose API secrets to code from a fork. See [GitHub Action docs](github-action.md) for details.

### How do I pin the PromptDrift version in CI?

```yaml
- uses: tanveer-arch/promptdrift/action@v1
  with:
    version: "promptdrift==0.1.0"
```

### Can I run multiple config files?

Not in a single invocation. Run `promptdrift test -c config1.yaml` and `promptdrift test -c config2.yaml` separately, or use multiple workflow jobs.

## Troubleshooting

### `promptdrift doctor` shows a failing check

Run `promptdrift doctor --verbose` for a detailed traceback. Common causes:
- Missing prompt file referenced in config
- API key env var not set
- Corrupted baseline JSON

### Tests pass locally but fail in CI

Run `promptdrift doctor` in CI as a diagnostic step. Check:
- Is the API key secret set correctly?
- Are prompt files checked into the repository?
- Is the Python version compatible (3.11+)?
