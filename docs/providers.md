# Providers

Providers are normalized adapters that connect PromptDrift to LLM backends. Each provider translates PromptDrift's internal request into the backend's API format and returns a standardized `ModelResponse`.

## OpenAI

Calls the [Chat Completions API](https://platform.openai.com/docs/api-reference/chat) using `httpx` — no OpenAI SDK dependency required.

### Configuration

```yaml
provider:
  type: openai
  model: gpt-4.1-mini
  api_key_env: OPENAI_API_KEY  # defaults to OPENAI_API_KEY if omitted
  base_url: https://api.openai.com/v1  # optional, for proxies or compatible APIs
```

### Supported response shape

The adapter accepts non-streaming Chat Completions responses containing at least one
choice with a `message.content` string. The top-level `usage`, `model`, and
`system_fingerprint` fields are optional; when absent, the corresponding normalized
values remain unknown.

Responses without `choices`, with an empty `choices` array, without a
`message.content` string, or with malformed JSON are rejected with a safe
`ProviderError`. Tool-only, multimodal, and other non-text response shapes are
intentionally unsupported.

Provider error messages do not include response bodies, so malformed or invalid
responses cannot expose provider-returned prompt/output data through the error.

### Environment

```bash
export OPENAI_API_KEY="sk-..."
```

### Compatible APIs

Use endpoints implementing the supported text Chat Completions request/response shape. Compatibility depends on support for `temperature`, `max_tokens` and string message content; tool-only/multimodal responses and every model variant are not supported. Set `base_url` explicitly:

```yaml
provider:
  type: openai
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
  api_key_env: DEEPSEEK_API_KEY
```

### Security

- API keys are **never** read from the config file — only from environment variables.
- Provider error messages **never** include request bodies or credentials.
- The `doctor` command checks whether the environment variable is set without printing the value.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `OPENAI_API_KEY is not set` | Env var missing | `export OPENAI_API_KEY="sk-..."` |
| `OpenAI request failed: HTTPStatusError` | Invalid key or quota | Check key at platform.openai.com |
| `OpenAI request failed: ConnectError` | Network issue or wrong `base_url` | Check your network and endpoint |

## Anthropic

Calls the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) (`/v1/messages`) using `httpx` — no Anthropic SDK dependency required.

### Configuration

```yaml
provider:
  type: anthropic
  model: claude-3-5-sonnet-latest
  api_key_env: ANTHROPIC_API_KEY  # defaults to ANTHROPIC_API_KEY if omitted
  system: You are a concise support assistant.  # optional system prompt
  base_url: https://api.anthropic.com/v1  # optional, for proxies
```

The `system` value is sent in the top level `system` field of the request. When it is omitted, no system prompt is sent. The rendered test prompt is always sent as a single user message.

### Environment

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Supported response shape

The adapter accepts non-streaming Messages API responses. Text is built by joining every `text` block in `content`; other block types, such as tool use, are ignored. Token usage is read from `usage.input_tokens` and `usage.output_tokens`, and the returned `model` is recorded as the resolved model. Cost is unknown.

Responses with invalid JSON, or with no text content, are rejected with a safe `ProviderResponseError`. Streaming and tool use execution are not supported.

Anthropic accepts a `temperature` between 0 and 1. Values above 1 are rejected by the API with a client error.

### Error mapping

| HTTP status or failure | PromptDrift error | Retried |
| --- | --- | --- |
| 401, 403 | `ProviderAuthError` | No |
| 429, 529 (overloaded) | `ProviderRateLimitError` | Yes |
| 500, 502, 503, 504 | `ProviderTransportError` | Yes |
| Other 4xx | `ProviderResponseError` | No |
| Timeout | `ProviderTimeoutError` | Yes |
| Connection failure | `ProviderTransportError` | Yes |
| Invalid JSON or empty content | `ProviderResponseError` | No |

Retries follow the shared resilience settings (`max_retries`, `initial_backoff`, and so on). Error messages contain only the provider name and the status or exception type. They never include API keys or response bodies.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ANTHROPIC_API_KEY is not set` | Env var missing | `export ANTHROPIC_API_KEY="sk-ant-..."` |
| `Anthropic request failed: HTTPStatusError (401)` | Invalid key | Check the key in the Anthropic console |
| `Anthropic request failed: HTTPStatusError (529 Overloaded)` | API is overloaded | Retry later or set `max_retries` |
| `Anthropic request failed: HTTPStatusError (400)` | Bad model name or temperature above 1 | Check `model` and `defaults.temperature` |

## Ollama

Calls the [Ollama Generate API](https://github.com/ollama/ollama/blob/main/docs/api.md) for local model inference.

### Configuration

```yaml
provider:
  type: ollama
  model: llama3.2
  base_url: http://localhost:11434  # default
```

### Setup

1. [Install Ollama](https://ollama.com/download)
2. Pull a model: `ollama pull llama3.2`
3. Ollama runs automatically; verify with `ollama list`

No API key is needed — Ollama runs locally.

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Ollama request failed: ConnectError` | Ollama not running | Start with `ollama serve` |
| `Ollama request failed: HTTPStatusError` | Model not pulled | `ollama pull <model>` |
| Slow responses | Large model on limited hardware | Use a smaller model like `llama3.2:1b` |


### Supported response shape

The adapter sends a non-streaming request to the Generate API and requires a
string `response` field. The returned `model`, `prompt_eval_count`, and
`eval_count` fields are optional; each absent field remains unknown. Malformed values produce a safe provider error. The
Chat API `message` envelope, streamed JSON-lines responses, and non-text
completions are unsupported. Other response fields are ignored and are never
copied into monitoring history.

## Mock

A deterministic local provider for testing and onboarding. It echoes the rendered prompt back as the output — no network calls, no API keys.

### Configuration

```yaml
provider:
  type: mock
  model: local-echo
```

### Behavior

- **Output:** The prompt text, whitespace-normalized and trimmed.
- **Tokens:** Estimated from word count.
- **Latency:** Measured local processing time; no performance guarantee.
- **Cost:** Always `$0.00`.

### Use Cases

- Running `promptdrift init` without any setup
- Testing the PromptDrift workflow in CI without spending API credits
- Writing and debugging assertions before connecting a real provider

## Monitoring behavior and limits

OpenAI-compatible, Anthropic and Ollama adapters normalize malformed response payloads into safe `ProviderError`s rather than treating missing text as a successful empty answer. The engine records optional provider-returned resolved model IDs/system fingerprints as hashes, without assuming they prove a model update. OpenAI-compatible and Anthropic cost is unknown unless future explicit pricing is implemented; configured cost limits therefore cannot silently pass.

Timeouts are currently fixed at 60 seconds (OpenAI) and 90 seconds (Ollama). Calls are sequential with no automatic retries. Repeated monitoring probes are explicitly budgeted observations, not hidden retries. No hosted provider was exercised by the offline test suite.

## Adding a Custom Provider

Providers implement a single interface:

```python
from promptdrift.providers.base import Provider
from promptdrift.models.result import ModelResponse


class MyProvider(Provider):
    def complete(self, prompt: str, *, temperature: float, max_output_tokens: int) -> ModelResponse:
        # Call your backend and return a normalized response
        ...
```

Register it in `providers/__init__.py` and add the type string to `ProviderConfig`.
