# Changelog

All notable changes to PromptDrift are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-20

### Added

- **CLI commands:** `init`, `test`, `baseline`, `diff`, `report`, `doctor`, `version`.
- **Providers:** OpenAI (Chat Completions), Ollama (local inference), and Mock (deterministic offline).
- **Deterministic assertions:** `exact_match`, `contains`, `not_contains`, `regex`, `not_regex`, `json_valid`, `json_schema`, `min_length`, `max_length`, `max_tokens`, `latency_ms`, `cost_usd`.
- **Baseline system:** SHA-256 output hashing, metrics tracking, and regression comparison without raw output storage.
- **Performance thresholds:** `latency_ms` and `cost_usd` with configurable warn/fail levels.
- **Reports:** Rich terminal tables, offline HTML, GitHub Step Summary, and PR comment markdown.
- **GitHub Action:** Composite action with Step Summary, JSON artifact upload, and optional PR commenting.
- **CI workflows:** Automated testing with pytest + ruff on push and pull request.
- **Release workflow:** Trusted PyPI publishing via GitHub OIDC — no stored tokens.
- **Template engine:** Jinja2 sandboxed rendering with strict undefined variable detection.
- **Local history:** Optional SQLite run storage with raw output suppression by default.
- **Privacy:** No telemetry, no hosted service, API keys from environment only.
- **Examples:** Customer support, structured JSON, and summarization use cases.
- **Documentation:** Getting started, configuration reference, assertions guide, providers, baselines, GitHub Action, architecture, and FAQ.
