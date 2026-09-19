"""Deterministic contract suggestion engine."""

from __future__ import annotations

import json
from collections.abc import Sequence

from promptdrift.models.capture import Interaction, Scenario
from promptdrift.models.test import Assertion


def suggest_assertions_for_scenario(
    scenario: Scenario,
    interactions: Sequence[Interaction] | None = None,
) -> list[Assertion]:
    """Suggest invariant assertions deterministically from outputs and inputs."""
    assertions: list[Assertion] = []

    # Filter interactions related to this scenario
    related = [
        i
        for i in (interactions or [])
        if i.prompt == scenario.prompt or i.input.strip().lower() == scenario.input.strip().lower()
    ]

    outputs = [i.output for i in related if i.output]

    if not outputs:
        # Default safety assertions
        assertions.append(Assertion(type="min_length", value=10, severity="fail"))
        assertions.append(Assertion(type="max_length", value=2000, severity="warn"))
        return assertions

    # 1. Check if all outputs are valid JSON
    all_json = True
    json_keys_set: list[set[str]] = []
    for out in outputs:
        try:
            val = json.loads(out)
            if isinstance(val, dict):
                json_keys_set.append(set(val.keys()))
            else:
                all_json = False
        except Exception:
            all_json = False
            break

    if all_json and json_keys_set:
        assertions.append(Assertion(type="json_valid", severity="fail"))
        common_keys = set.intersection(*json_keys_set)
        if common_keys:
            schema = {
                "type": "object",
                "required": sorted(list(common_keys)),
            }
            assertions.append(Assertion(type="json_schema", schema=schema, severity="fail"))

    # 2. Length bounds
    lengths = [len(o) for o in outputs]
    min_len = min(lengths)
    max_len = max(lengths)

    safe_min = max(5, int(min_len * 0.7))
    safe_max = max(int(max_len * 1.5), safe_min + 50)
    assertions.append(Assertion(type="min_length", value=safe_min, severity="fail"))
    assertions.append(Assertion(type="max_length", value=safe_max, severity="warn"))

    # 3. Category specific patterns
    cat = (scenario.category or "").lower()
    if "refund" in cat:
        # Policy window check suggestion
        assertions.append(
            Assertion(type="not_contains", value="guaranteed 100% refund", severity="fail")
        )
    elif "escalat" in cat:
        assertions.append(
            Assertion(
                type="regex", value=r"(?i)(agent|representative|team|support)", severity="fail"
            )
        )

    return assertions
