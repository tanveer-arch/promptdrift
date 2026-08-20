# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |

## Reporting a Vulnerability

If you discover a security vulnerability in PromptDrift, please report it responsibly:

1. **Do not** open a public issue.
2. Email the maintainers or use [GitHub's private vulnerability reporting](https://github.com/tanveer-arch/promptdrift/security/advisories/new).
3. Include a description of the vulnerability, steps to reproduce, and potential impact.

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Design

PromptDrift is designed with security and privacy as core principles:

### No Telemetry
PromptDrift does not collect, transmit, or store any analytics or usage data. There is no hosted service, no phone-home behavior, and no third-party tracking.

### API Key Handling
- API keys are **never** read from configuration files — only from environment variables.
- The config file stores only the **name** of the environment variable (e.g., `api_key_env: OPENAI_API_KEY`).
- Provider error messages **never** include request bodies, response bodies, or credentials.
- The `doctor` command checks whether a key is set without printing the value.

### Baseline Safety
- Baseline files store **SHA-256 hashes** of outputs, not raw content.
- Raw prompts and outputs are suppressed in local SQLite history by default.
- Baselines are safe to commit to public repositories.

### Template Sandboxing
- Prompt templates are rendered in a [Jinja2 SandboxedEnvironment](https://jinja.palletsprojects.com/en/3.1.x/sandbox/).
- Templates cannot access the filesystem, execute code, or import modules.

### CI Security
- The GitHub Action uses `pull_request` (not `pull_request_target`) by default.
- PR commenting is automatically disabled for fork PRs.
- See [GitHub Action docs](docs/github-action.md) for fork security guidance.

## Scope

The following are **in scope** for security reports:
- Credential exposure through error messages, logs, or reports
- Template sandbox escapes
- Baseline files leaking raw prompt or output content
- Dependency vulnerabilities that affect PromptDrift users

The following are **out of scope**:
- Vulnerabilities in LLM providers themselves (OpenAI, Ollama)
- Prompt injection attacks against the LLM (not a PromptDrift concern)
- Issues in the user's own prompt templates
