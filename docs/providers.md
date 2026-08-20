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

### Environment

```bash
export OPENAI_API_KEY="sk-..."
```

### Compatible APIs

Any API that implements the OpenAI Chat Completions format works — set `base_url` to the provider's endpoint:

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

## Mock

A deterministic, zero-latency provider for testing and onboarding. It echoes the rendered prompt back as the output — no network calls, no API keys.

### Configuration

```yaml
provider:
  type: mock
  model: local-echo
```

### Behavior

- **Output:** The prompt text, whitespace-normalized and trimmed.
- **Tokens:** Estimated from word count.
- **Latency:** Near-zero (measured but typically <1ms).
- **Cost:** Always `$0.00`.

### Use Cases

- Running `promptdrift init` without any setup
- Testing the PromptDrift workflow in CI without spending API credits
- Writing and debugging assertions before connecting a real provider

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
