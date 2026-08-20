# Getting started

Install PromptDrift, run `promptdrift init`, then `promptdrift test`. The generated project uses the deterministic offline `mock` provider. Change `provider.type` to `openai` or `ollama` when ready, create a baseline with `promptdrift baseline`, and commit it.

## Publishing a release

Configure this repository as a PyPI trusted publisher for the `promptdrift` project, then push a `v*` tag. The release workflow tests, lints, builds, and publishes with GitHub's OIDC token; no long-lived PyPI token is stored in the repository.
