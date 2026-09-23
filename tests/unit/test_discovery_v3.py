"""Tests for v0.3 scenario discovery: stable fingerprinting, deduplication, lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime

from promptdrift.engine.discovery import (
    _compute_fingerprint,
    _normalize,
    discover_scenarios,
)
from promptdrift.models.capture import Interaction, Scenario, ScenarioLibrary
from promptdrift.storage.scenarios import add_or_update_scenarios, save_scenarios


class TestFingerprinting:
    def test_normalize_strips_and_lowercases(self):
        assert _normalize("  Hello  World  ") == "hello world"

    def test_same_input_same_fingerprint(self):
        fp1 = _compute_fingerprint("p.txt", "Hello world", {})
        fp2 = _compute_fingerprint("p.txt", "Hello world", {})
        assert fp1 == fp2

    def test_different_input_different_fingerprint(self):
        fp1 = _compute_fingerprint("p.txt", "How do I get a refund?", {})
        fp2 = _compute_fingerprint("p.txt", "How do I cancel my order?", {})
        assert fp1 != fp2

    def test_different_prompt_different_fingerprint(self):
        fp1 = _compute_fingerprint("support.txt", "Hello", {})
        fp2 = _compute_fingerprint("billing.txt", "Hello", {})
        assert fp1 != fp2

    def test_variables_affect_fingerprint(self):
        fp1 = _compute_fingerprint("p.txt", "Hello", {"lang": "en"})
        fp2 = _compute_fingerprint("p.txt", "Hello", {"lang": "fr"})
        assert fp1 != fp2

    def test_whitespace_normalized(self):
        fp1 = _compute_fingerprint("p.txt", "Hello  world", {})
        fp2 = _compute_fingerprint("p.txt", "hello world", {})
        assert fp1 == fp2

    def test_edge_cases_remain_separate(self):
        """Different refund edge cases must remain separate scenarios."""
        fp_full = _compute_fingerprint("p.txt", "I want a full refund for my broken item", {})
        fp_partial = _compute_fingerprint("p.txt", "Can I get a partial refund?", {})
        fp_expired = _compute_fingerprint("p.txt", "My refund window expired, help", {})
        assert fp_full != fp_partial
        assert fp_full != fp_expired
        assert fp_partial != fp_expired


class TestDiscoverScenarios:
    def test_groups_identical_interactions(self):
        interactions = [
            Interaction(
                id="1",
                provider="m",
                model="m",
                prompt="p.txt",
                input="Hello world",
                output="Hi there",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            Interaction(
                id="2",
                provider="m",
                model="m",
                prompt="p.txt",
                input="Hello world",
                output="Hello!",
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            ),
        ]
        scenarios = discover_scenarios(interactions)
        assert len(scenarios) == 1
        assert scenarios[0].sample_count == 2

    def test_different_inputs_separate_scenarios(self):
        interactions = [
            Interaction(
                id="1",
                provider="m",
                model="m",
                prompt="p.txt",
                input="I want a refund for my broken item",
                output="Refund info",
                tags=["refund"],
            ),
            Interaction(
                id="2",
                provider="m",
                model="m",
                prompt="p.txt",
                input="Where is my refund?",
                output="Check status",
                tags=["refund"],
            ),
            Interaction(
                id="3",
                provider="m",
                model="m",
                prompt="p.txt",
                input="Speak to human representative",
                output="Connecting",
                tags=["escalation"],
            ),
        ]
        scenarios = discover_scenarios(interactions)
        # Three different inputs → three different scenarios
        assert len(scenarios) == 3

    def test_stable_ids_across_runs(self):
        """Same interactions in different order should produce same scenario IDs."""
        interactions = [
            Interaction(
                id="1",
                provider="m",
                model="m",
                prompt="p.txt",
                input="Hello world",
                output="Hi",
            ),
        ]
        scenarios1 = discover_scenarios(interactions)
        scenarios2 = discover_scenarios(interactions)
        assert scenarios1[0].id == scenarios2[0].id
        assert scenarios1[0].fingerprint == scenarios2[0].fingerprint

    def test_first_seen_last_seen_tracked(self):
        interactions = [
            Interaction(
                id="1",
                provider="m",
                model="m",
                prompt="p.txt",
                input="test",
                output="out",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            Interaction(
                id="2",
                provider="m",
                model="m",
                prompt="p.txt",
                input="test",
                output="out2",
                timestamp=datetime(2024, 6, 15, tzinfo=UTC),
            ),
        ]
        scenarios = discover_scenarios(interactions)
        assert len(scenarios) == 1
        assert scenarios[0].first_seen == datetime(2024, 1, 1, tzinfo=UTC)
        assert scenarios[0].last_seen == datetime(2024, 6, 15, tzinfo=UTC)

    def test_category_inferred(self):
        interactions = [
            Interaction(
                id="1",
                provider="m",
                model="m",
                prompt="p.txt",
                input="I want a refund",
                output="ok",
            ),
        ]
        scenarios = discover_scenarios(interactions)
        assert scenarios[0].category == "refund"


class TestPromotedScenarioProtection:
    def test_promoted_scenario_not_modified(self, tmp_path):
        path = tmp_path / "scenarios.json"

        # Create a promoted scenario
        promoted = Scenario(
            id="refund_case_abc12345",
            prompt="p.txt",
            input="I want a refund",
            category="refund",
            status="promoted",
            assertions=[],
            fingerprint="abc12345deadbeef",
            sample_count=5,
        )
        lib = ScenarioLibrary(version=1, scenarios=[promoted])
        save_scenarios(lib, path)

        # Discover new interactions that match the same fingerprint
        new_scenarios = [
            Scenario(
                id="refund_case_abc12345",
                prompt="p.txt",
                input="I want a refund",
                category="refund",
                status="candidate",
                fingerprint="abc12345deadbeef",
                sample_count=10,
                last_seen=datetime(2024, 12, 1, tzinfo=UTC),
            ),
        ]

        result = add_or_update_scenarios(new_scenarios, path)
        matched = next(s for s in result.scenarios if s.id == "refund_case_abc12345")

        # Status must remain promoted
        assert matched.status == "promoted"
        # sample_count must NOT be updated
        assert matched.sample_count == 5

    def test_candidate_metadata_updated(self, tmp_path):
        path = tmp_path / "scenarios.json"

        existing = Scenario(
            id="test_case_abc12345",
            prompt="p.txt",
            input="test input",
            status="candidate",
            fingerprint="abc12345deadbeef",
            sample_count=3,
            first_seen=datetime(2024, 1, 1, tzinfo=UTC),
            last_seen=datetime(2024, 6, 1, tzinfo=UTC),
        )
        lib = ScenarioLibrary(version=1, scenarios=[existing])
        save_scenarios(lib, path)

        new_scenarios = [
            Scenario(
                id="test_case_abc12345",
                prompt="p.txt",
                input="test input",
                status="candidate",
                fingerprint="abc12345deadbeef",
                sample_count=7,
                first_seen=datetime(2023, 6, 1, tzinfo=UTC),
                last_seen=datetime(2024, 12, 1, tzinfo=UTC),
            ),
        ]

        result = add_or_update_scenarios(new_scenarios, path)
        matched = next(s for s in result.scenarios if s.id == "test_case_abc12345")

        assert matched.sample_count == 7
        assert matched.first_seen == datetime(2023, 6, 1, tzinfo=UTC)
        assert matched.last_seen == datetime(2024, 12, 1, tzinfo=UTC)

    def test_new_scenario_added(self, tmp_path):
        path = tmp_path / "scenarios.json"
        lib = ScenarioLibrary(version=1, scenarios=[])
        save_scenarios(lib, path)

        new_scenarios = [
            Scenario(
                id="brand_new_abc12345",
                prompt="p.txt",
                input="brand new input",
                fingerprint="newfingerprint1",
            ),
        ]

        result = add_or_update_scenarios(new_scenarios, path)
        assert len(result.scenarios) == 1
        assert result.scenarios[0].id == "brand_new_abc12345"
