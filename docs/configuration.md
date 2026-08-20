# Configuration

PromptDrift is configured through a single `promptdrift.yaml` file. The schema is strict and versioned — unknown fields cause a validation error rather than being silently ignored.

## Full Annotated Example

```yaml
# Schema version (currently only 1)
version: 1

# LLM provider configuration
provider:
  type: openai              # "openai" | "ollama" | "mock"
  model: gpt-4.1-mini       # Model identifier
  api_key_env: OPENAI_API_KEY  # Environment variable name (OpenAI only)
  base_url: null             # Override API endpoint (optional)

# Default parameters applied to every test
defaults:
  temperature: 0             # 0–2, lower = more deterministic
  max_output_tokens: 500     # Maximum tokens in the response

# Baseline configuration
baseline:
  path: promptdrift.baseline.json  # Relative to config file
  store_raw_output: false          # If true, store raw output in local SQLite

# CI failure policy
ci:
  fail_on:
    - assertion_failure      # Fail the build on assertion violations
  warn_on:
    - semantic_change        # Warn when output changes
    - latency_regression     # Warn on latency increase

# Test cases
tests:
  - id: refund_request       # Unique identifier (alphanumeric, _, ., -)
    prompt: prompts/support.txt  # Jinja2 template path (relative to config)
    variables:               # Template variables
      policy: "Refunds are available within 30 days."
      question: "Can I get a refund for my order?"
    assertions:              # Behavioral contracts
      - type: contains
        value: "30 days"
      - type: not_contains
        value: guaranteed
        severity: warn       # "fail" (default) or "warn"
      - type: max_length
        value: 600
    thresholds:              # Performance thresholds
      latency_ms: 5000       # Number = failure threshold
      cost_usd:
        warn: 0.01           # Structured threshold
        fail: 0.05
```

## Field Reference

### Top Level

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `version` | `1` | Yes | — | Schema version, must be `1` |
| `provider` | object | Yes | — | LLM provider configuration |
| `defaults` | object | No | See below | Default generation parameters |
| `baseline` | object | No | See below | Baseline file settings |
| `ci` | object | No | See below | CI failure/warning policy |
| `tests` | list | Yes | — | At least one test case required |

### Provider

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `type` | string | Yes | — | `"openai"`, `"ollama"`, or `"mock"` |
| `model` | string | No | `"mock"` | Model name or identifier |
| `api_key_env` | string | No | `null` | Environment variable holding the API key |
| `base_url` | string | No | `null` | Custom API endpoint URL |

### Defaults

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `temperature` | float | `0` | Sampling temperature (0–2) |
| `max_output_tokens` | int | `500` | Maximum output token count |

### Test Case

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | string | Yes | — | Unique test identifier |
| `prompt` | string | Yes | — | Path to the Jinja2 prompt template |
| `variables` | dict | No | `{}` | Key-value pairs passed to the template |
| `assertions` | list | No | `[]` | Deterministic behavioral contracts |
| `thresholds` | dict | No | `{}` | `latency_ms` and `cost_usd` limits |

### Assertion

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `type` | string | Yes | — | Assertion type (see [Assertions](assertions.md)) |
| `value` | any | Depends | — | Expected value (not required for `json_valid`) |
| `schema` | dict | `json_schema` only | — | JSON Schema object |
| `name` | string | No | type name | Human-readable label in reports |
| `severity` | string | No | `"fail"` | `"fail"` or `"warn"` |

## Path Resolution

All paths in the configuration (`prompt`, `baseline.path`) are resolved **relative to the config file**, not the working directory. Absolute paths are used as-is.

## Validation

PromptDrift uses strict Pydantic models with `extra="forbid"`. Any typo or unknown field triggers a clear validation error at load time — not a silent runtime surprise.
