"""Deterministic scenario discovery with stable fingerprinting.

Scenarios are identified by a deterministic hash of (prompt, full_input, variables).
Different edge cases with different input text produce separate scenarios.
Repeated identical interactions increment sample_count / update last_seen.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence

from promptdrift.models.capture import Interaction, Scenario


def _normalize(text: str) -> str:
    """Normalize text for fingerprinting: strip, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _compute_fingerprint(prompt: str, input_text: str, variables: dict) -> str:
    """Deterministic fingerprint from prompt identity + full input + variables."""
    canonical_vars = json.dumps(variables, sort_keys=True, default=str)
    raw = f"{_normalize(prompt)}\x00{_normalize(input_text)}\x00{canonical_vars}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:30] or "scenario"


def _infer_category(input_text: str, tags: list[str]) -> str:
    if tags:
        return tags[0]

    text = input_text.lower()
    keywords = [
        ("refund", ["refund", "money back", "return", "chargeback"]),
        ("cancellation", ["cancel", "unsubscribe", "stop service"]),
        ("escalation", ["human", "agent", "supervisor", "representative", "manager"]),
        ("order-status", ["status", "where is", "tracking", "delivery", "shipped"]),
        ("billing", ["invoice", "payment", "bill", "receipt"]),
        ("auth", ["login", "password", "reset", "2fa", "account"]),
    ]
    for category, terms in keywords:
        if any(term in text for term in terms):
            return category
    return "general"


def _make_scenario_id(fingerprint: str, category: str, input_text: str) -> str:
    """Generate a stable, readable scenario ID from fingerprint."""
    prefix = _slugify(category)
    suffix = _slugify(input_text[:20])
    # Use first 8 chars of fingerprint for uniqueness
    return f"{prefix}_{suffix}_{fingerprint[:8]}"


def discover_scenarios(interactions: Sequence[Interaction]) -> list[Scenario]:
    """Group interactions by deterministic fingerprint into candidate scenarios.

    Each unique (prompt, full_input, variables) combination produces one scenario.
    Repeated interactions increment sample_count and update timestamps.
    """
    # Group by fingerprint
    fingerprint_map: dict[str, list[Interaction]] = {}
    for interaction in interactions:
        fp = _compute_fingerprint(interaction.prompt, interaction.input, interaction.variables)
        fingerprint_map.setdefault(fp, []).append(interaction)

    candidates: list[Scenario] = []

    for fp, items in fingerprint_map.items():
        # Use most recent as representative
        items_sorted = sorted(items, key=lambda x: x.timestamp, reverse=True)
        representative = items_sorted[0]
        oldest = items_sorted[-1]

        cat = _infer_category(representative.input, representative.tags)
        scenario_id = _make_scenario_id(fp, cat, representative.input)

        candidates.append(
            Scenario(
                id=scenario_id,
                prompt=representative.prompt,
                input=representative.input,
                variables=representative.variables,
                category=cat,
                tags=representative.tags,
                source="capture",
                status="candidate",
                assertions=[],
                thresholds={},
                created_at=oldest.timestamp,
                sample_count=len(items),
                first_seen=oldest.timestamp,
                last_seen=representative.timestamp,
                fingerprint=fp,
            )
        )

    return candidates
