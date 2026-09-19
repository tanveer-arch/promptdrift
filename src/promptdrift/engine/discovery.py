"""Deterministic scenario discovery and grouping from captured interactions."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from promptdrift.models.capture import Interaction, Scenario


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


def discover_scenarios(interactions: Sequence[Interaction]) -> list[Scenario]:
    """Group interactions deterministically into candidate scenarios by prompt and category."""
    grouped: dict[str, list[Interaction]] = defaultdict(list)

    for interaction in interactions:
        cat = _infer_category(interaction.input, interaction.tags)
        group_key = f"{interaction.prompt}::{cat}"
        grouped[group_key].append(interaction)

    candidates: list[Scenario] = []
    seen_ids: set[str] = set()

    for group_key, items in grouped.items():
        # Pick the most representative item (longest/most descriptive)
        items_sorted = sorted(items, key=lambda x: (len(x.input), x.timestamp), reverse=True)
        representative = items_sorted[0]
        cat = _infer_category(representative.input, representative.tags)

        base_id = f"{_slugify(cat)}_{_slugify(representative.input[:20])}"
        candidate_id = base_id
        counter = 1
        while candidate_id in seen_ids:
            candidate_id = f"{base_id}_{counter:03d}"
            counter += 1
        seen_ids.add(candidate_id)

        candidates.append(
            Scenario(
                id=candidate_id,
                prompt=representative.prompt,
                input=representative.input,
                variables=representative.variables,
                category=cat,
                tags=representative.tags,
                source="capture",
                status="candidate",
                assertions=[],
                thresholds={},
                created_at=representative.timestamp,
            )
        )

    return candidates
