# Getting Started

This guide walks you through installing PromptDrift, running your first test, and creating a baseline — all without an API key.

## Prerequisites

- **Python 3.11+** — check with `python --version`
- **pip** — included with Python

## Install

```bash
pip install promptdrift
```

Or install from source for development:

```bash
git clone https://github.com/tanveer-arch/promptdrift.git
cd promptdrift
pip install -e ".[dev]"
```

## Create a Starter Project

```bash
mkdir my-prompts && cd my-prompts
promptdrift init
```

This creates two files:

| File | Purpose |
| --- | --- |
| `promptdrift.yaml` | Test configuration with one example test |
| `prompts/example.txt` | A Jinja2 prompt template |

The starter project uses the **mock provider**, so no API key is needed.

## Run Your First Test

```bash
promptdrift test
```

You should see:

```
┌───────────────────────────────────┐
│          PromptDrift              │
├──────┬────────┬───────────────────┤
│ Test │ Status │ Reason            │
├──────┼────────┼───────────────────┤
│hello │ PASS   │All assertions pass│
└──────┴────────┴───────────────────┘
1 passed - 0 warnings - 0 failed
```

## Capture a Baseline

Once you're happy with the output, lock it in:

```bash
promptdrift baseline
git add promptdrift.baseline.json
git commit -m "Add PromptDrift baseline"
```

The baseline stores hashes and metrics — never raw prompt content or secrets.

## Compare Against the Baseline

After changing a prompt, run:

```bash
promptdrift diff
```

PromptDrift compares the new output against the baseline and reports whether any **behavioral contracts** were violated. A wording change alone does not cause a failure — only a broken assertion does.

## Switch to a Real Provider

Edit `promptdrift.yaml` to use OpenAI or Ollama:

```yaml
provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY
```

Set the environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

Then re-run `promptdrift test`.

## Check Your Setup

```bash
promptdrift doctor
```

This validates your config, prompt files, API keys, and baseline health — useful before setting up CI.

## Next Steps

- [Configuration reference](configuration.md) — every field in `promptdrift.yaml`
- [Assertions](assertions.md) — all supported contract types
- [GitHub Action](github-action.md) — run PromptDrift on every PR
- [Providers](providers.md) — OpenAI, Ollama, and mock setup

## Publishing a Release

Configure this repository as a PyPI trusted publisher for the `promptdrift` project, then push a `v*` tag. The release workflow tests, lints, builds, and publishes with GitHub's OIDC token; no long-lived PyPI token is stored in the repository.
