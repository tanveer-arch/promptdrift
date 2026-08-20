# Architecture

The CLI loads strict models, renders templates in a sandbox, calls a normalized provider adapter, evaluates independent deterministic contracts, compares optional Git baseline hashes, and renders terminal/JSON/HTML/GitHub reports. SQLite is best-effort local history only; the baseline is canonical.
