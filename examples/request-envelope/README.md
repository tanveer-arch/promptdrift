# Request-Envelope Provenance Example

This example demonstrates how PromptDrift uses a **Request Envelope** to capture external context (system instructions, tool definitions, RAG retrieval context, and explicitly declared uncaptured state) into per-case provenance without storing sensitive raw data.

## Why Request Envelopes?

In modern LLM applications (RAG pipelines, agents with tools), model outputs depend on more than just the prompt template. If a tool parameter changes or retrieval returns different document chunks, observing output changes is **confounded**: the change was caused by input drift, not vendor model drift.

The `request_envelope` allows PromptDrift to differentiate between:
- **Comparable runs**: Identical prompt, system instructions, tools, and retrieval context $\rightarrow$ any behavioral failure is attributed to model behavior (`observed_model_drift`).
- **Confounded runs**: A tool schema or retrieval context changed $\rightarrow$ correctly triaged as `prompt_changed`.

## Walkthrough

### 1. Create a Baseline
```bash
promptdrift baseline -c promptdrift.yaml
```
PromptDrift captures SHA-256 hashes for each envelope component:
- `request_envelope.system`
- `request_envelope.tools`
- `request_envelope.retrieval_context`
- `request_envelope.uncaptured`

### 2. Comparable Run (No Envelope Changes)
```bash
promptdrift monitor -c promptdrift.yaml
```
Since the prompt and all envelope components match the baseline, PromptDrift confirms that monitored inputs are stationary.

### 3. Confounded Run (Tool Schema or RAG Context Changed)
If the tool schema changes (e.g. adding a new parameter) or retrieval returns updated document chunks, `promptdrift monitor` isolates the exact drifted component:
```text
Diagnosis: prompt_changed
Evidence: request_envelope.tools differs from the accepted baseline.
```
This protects developers from wrongly attributing infrastructure or context changes to vendor LLM drift.
