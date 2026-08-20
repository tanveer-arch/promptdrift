# Configuration

`promptdrift.yaml` is strict and versioned (`version: 1`). It contains one provider, defaults, a baseline path, CI policy, and test cases. Prompt paths are resolved relative to the configuration file. Unknown fields are validation errors.

`thresholds` accepts `latency_ms` and `cost_usd`; each can be a number (failure) or `{warn: ..., fail: ...}`.
