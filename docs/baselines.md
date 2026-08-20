# Baselines

Baselines are the canonical snapshot of your LLM's known-good behavior. They let PromptDrift detect **behavioral regressions** without treating every wording change as a failure.

## Lifecycle

```
1. Run tests           →  promptdrift test
2. Review output       →  Verify behavior is correct
3. Capture baseline    →  promptdrift baseline
4. Commit to Git       →  git add promptdrift.baseline.json
5. Change a prompt     →  Edit prompts/*.txt
6. Compare             →  promptdrift diff
7. Update baseline     →  promptdrift baseline --force
```

## Creating a Baseline

```bash
promptdrift baseline
```

This runs all tests and writes `promptdrift.baseline.json` (or the path configured in `baseline.path`).

If a baseline already exists, the command fails with an error. Use `--force` to replace it:

```bash
promptdrift baseline --force
```

## What's Stored

The baseline contains **hashes and metrics**, not raw outputs or secrets:

```json
{
  "schema_version": 1,
  "promptdrift_version": "0.1.0",
  "generated_at": "2026-08-20T10:00:00Z",
  "provider": {
    "type": "openai",
    "model": "gpt-4.1-mini"
  },
  "tests": {
    "refund_request": {
      "output_hash": "a1b2c3d4...",
      "status": "PASS",
      "assertions": {
        "contains": true,
        "not_contains": true,
        "max_length": true
      },
      "metrics": {
        "latency_ms": 1234.56,
        "input_tokens": 45,
        "output_tokens": 120,
        "estimated_cost_usd": 0.002
      }
    }
  }
}
```

| Field | Purpose |
| --- | --- |
| `output_hash` | SHA-256 of the output text — detects changes without storing content |
| `status` | `PASS`, `WARN`, or `FAIL` at the time the baseline was captured |
| `assertions` | Per-assertion pass/fail results |
| `metrics` | Latency, tokens, and cost for regression tracking |

## How Comparison Works

When you run `promptdrift test` or `promptdrift diff` with an existing baseline:

1. **Contracts are evaluated first.** Assertions determine PASS/WARN/FAIL independently of the baseline.
2. **Output hash is compared.** If the hash changed but all assertions still pass, PromptDrift adds a diagnostic note — it does **not** fail the test.
3. **New tests are flagged.** A test ID that doesn't exist in the baseline gets a WARN with "Test has no baseline."

### What Causes a Failure

| Scenario | Result |
| --- | --- |
| Assertion violated | ❌ FAIL |
| Output changed, all assertions pass | ✅ PASS (with note) |
| New test not in baseline | ⚠️ WARN |
| Output identical to baseline | ✅ PASS |

## Committing the Baseline

The baseline file is designed to be version-controlled:

```bash
git add promptdrift.baseline.json
git commit -m "Update PromptDrift baseline"
```

Since it contains hashes (not raw outputs) and never stores API keys, it's safe to commit to public repositories.

## Local History

PromptDrift also stores run history in a local SQLite database (`~/.promptdrift/promptdrift.db`) for debugging. This is best-effort and not required — the baseline file is the canonical source of truth. Raw prompts and outputs are suppressed by default; set `baseline.store_raw_output: true` to keep them locally.
