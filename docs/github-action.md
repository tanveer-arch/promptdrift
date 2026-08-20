# GitHub Action

Use `promptdrift/action@v1` with an API key supplied through an environment secret. The Action writes a sanitized Markdown summary, uploads the full JSON report by default, and fails after reports are generated when contracts fail.

Set `comment: 'true'` only for same-repository pull requests and grant `pull-requests: write`. The Action refuses this path for forks. For forked PRs, use `pull_request`, do not expose provider secrets, and never run untrusted code with `pull_request_target` credentials.
