# GitHub Action

PromptDrift ships a composite GitHub Action that runs behavioral contracts on every pull request, writes a Step Summary, uploads a JSON report, and optionally posts a PR comment.

## Quick Start

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

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `config` | No | `promptdrift.yaml` | Path to the configuration file |
| `working-directory` | No | `.` | Directory in which to run PromptDrift |
| `version` | No | `promptdrift` | PyPI package version or spec |
| `upload-report` | No | `true` | Upload JSON report as a workflow artifact |
| `comment` | No | `false` | Update a single marked comment on the PR |

## Outputs

| Output | Description |
| --- | --- |
| `result` | Path to the JSON report file |

## What the Action Does

1. **Installs PromptDrift** from PyPI (or a pinned version).
2. **Runs `promptdrift diff`** — executes all tests and compares against the baseline.
3. **Writes a Step Summary** — a Markdown table visible in the Actions tab.
4. **Uploads the JSON report** — downloadable from the workflow artifacts.
5. **Fails the step** — only after reports are uploaded, so they're always available.

## Adding PR Comments

To post a formatted comment on the pull request:

```yaml
permissions:
  contents: read
  pull-requests: write  # Required for commenting

steps:
  - uses: actions/checkout@v4
  - uses: tanveer-arch/promptdrift/action@v1
    with:
      config: promptdrift.yaml
      comment: "true"
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

The Action creates or updates a **single** comment per PR (identified by an HTML marker), so it doesn't spam the conversation.

## Managing Secrets

1. Go to **Settings → Secrets and variables → Actions** in your GitHub repo.
2. Click **New repository secret**.
3. Name it `OPENAI_API_KEY` and paste your key.
4. Reference it in the workflow as `${{ secrets.OPENAI_API_KEY }}`.

> **Never** hardcode API keys in workflow files or configuration.

## Fork Security

PromptDrift follows GitHub's security recommendations for pull requests from forks:

| Event | Secrets available? | Safe for forks? |
| --- | --- | --- |
| `pull_request` | No | ✅ Yes — use the mock provider |
| `pull_request_target` | Yes | ❌ No — never run untrusted code with secrets |

The PR comment feature (`comment: 'true'`) is **automatically disabled** for forks — it checks `github.event.pull_request.head.repo.fork == false`.

For open source repos accepting fork PRs:
- Use `pull_request` (not `pull_request_target`)
- Run with the `mock` provider or skip provider-dependent tests
- Never expose secrets to code from a fork

## Using with the Mock Provider

For repos that don't need a real LLM provider in CI:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: tanveer-arch/promptdrift/action@v1
    with:
      config: promptdrift.yaml
    # No API key needed — mock provider runs locally
```

## Pinning the Version

To avoid unexpected breaks from new releases:

```yaml
- uses: tanveer-arch/promptdrift/action@v1
  with:
    version: "promptdrift==0.1.0"
```

## Troubleshooting

| Issue | Fix |
| --- | --- |
| `OPENAI_API_KEY is not set` | Add it as a repository secret |
| Action passes but PR comment missing | Grant `pull-requests: write` permission |
| Report not uploaded | Check `upload-report` is `"true"` (string, not boolean) |
| Tests pass locally but fail in CI | Run `promptdrift doctor` locally to check env parity |
