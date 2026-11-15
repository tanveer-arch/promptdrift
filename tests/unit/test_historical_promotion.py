"""Offline tests for validating and promoting captured historical observations."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from typer.testing import CliRunner

import promptdrift.cli as cli
from promptdrift.cli import app
from promptdrift.engine.discovery import discover_scenarios
from promptdrift.models.capture import Interaction, Scenario, ScenarioLibrary
from promptdrift.models.test import Assertion
from promptdrift.storage.scenarios import (
    add_or_update_scenarios as merge_scenarios,
)
from promptdrift.storage.scenarios import (
    load_scenarios,
    save_scenarios,
)
from promptdrift.storage.sqlite import get_interactions, record_interaction

runner = CliRunner()


def _bind_temporary_storage(monkeypatch, db_path, scenarios_path):
    monkeypatch.setattr(
        cli,
        "get_interactions",
        lambda limit=1000, strict=False: get_interactions(limit=limit, path=db_path, strict=strict),
    )
    monkeypatch.setattr(
        cli,
        "add_or_update_scenarios",
        lambda scenarios: merge_scenarios(scenarios, path=scenarios_path),
    )
    monkeypatch.setattr(
        cli, "load_scenarios", lambda strict=False: load_scenarios(scenarios_path, strict=strict)
    )
    monkeypatch.setattr(
        cli, "save_scenarios", lambda library: save_scenarios(library, scenarios_path)
    )


def _interaction(
    interaction_id: str = "obs-1",
    *,
    source: str = "manual",
    timestamp: datetime | None = None,
) -> Interaction:
    return Interaction(
        id=interaction_id,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=UTC),
        provider="mock",
        model="local-model",
        prompt="prompts/support.txt",
        input="How do I request a refund?",
        variables={"locale": "en"},
        output="You can request a refund within 30 days.",
        tags=["refund"],
        source=source,  # type: ignore[arg-type]
    )


def _learn(monkeypatch, tmp_path):
    db_path = tmp_path / "observations.sqlite3"
    scenarios_path = tmp_path / ".promptdrift" / "scenarios.json"
    _bind_temporary_storage(monkeypatch, db_path, scenarios_path)
    return db_path, scenarios_path


class TestHistoricalObservationPromotion:
    def test_promotes_valid_observation_and_preserves_provenance(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        observation = _interaction()
        record_interaction(observation, path=db_path)

        learned = runner.invoke(app, ["learn", "--json"])
        assert learned.exit_code == 0, learned.output
        learned_scenarios = json.loads(learned.output)
        assert len(learned_scenarios) == 1
        scenario_id = learned_scenarios[0]["id"]

        promoted = runner.invoke(app, ["promote", scenario_id])
        assert promoted.exit_code == 0, promoted.output

        scenario = load_scenarios(scenarios_path).scenarios[0]
        assert scenario.status == "promoted"
        assert scenario.source == "manual"
        assert scenario.provenance[0].interaction_id == observation.id
        assert scenario.provenance[0].provider == observation.provider
        assert scenario.provenance[0].model == observation.model
        assert scenario.provenance[0].source == observation.source
        assert scenario.provenance[0].timestamp == observation.timestamp
        assert scenario.assertions

    def test_rejects_malformed_observation_without_creating_candidates(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction(), path=db_path)
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE interactions SET variables_json = '{' WHERE id = 'obs-1'")

        result = runner.invoke(app, ["learn", "--json"])

        assert result.exit_code == 2
        assert "obs-1" in result.output
        assert "variables JSON" in result.output
        assert not scenarios_path.exists()

    def test_rejects_missing_required_metadata(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction(), path=db_path)
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE interactions SET provider = NULL WHERE id = 'obs-1'")

        result = runner.invoke(app, ["learn", "--json"])

        assert result.exit_code == 2
        assert "provider" in result.output
        assert "required metadata" in result.output
        assert not scenarios_path.exists()

    def test_rejects_missing_provenance(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction(), path=db_path)
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE interactions SET source = NULL WHERE id = 'obs-1'")

        result = runner.invoke(app, ["learn", "--json"])

        assert result.exit_code == 2
        assert "source" in result.output
        assert "required metadata" in result.output
        assert not scenarios_path.exists()

    def test_rejects_unsupported_provenance_source(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction(), path=db_path)
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE interactions SET source = 'remote' WHERE id = 'obs-1'")

        result = runner.invoke(app, ["learn", "--json"])

        assert result.exit_code == 2
        assert "source" in result.output
        assert "malformed or unsupported" in result.output
        assert not scenarios_path.exists()

    def test_deduplicates_historical_observations_by_identity(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction("obs-1"), path=db_path)
        first = runner.invoke(app, ["learn", "--json"])
        assert first.exit_code == 0, first.output

        record_interaction(
            _interaction("obs-2", timestamp=datetime(2026, 1, 2, tzinfo=UTC)),
            path=db_path,
        )

        second = runner.invoke(app, ["learn", "--json"])
        third = runner.invoke(app, ["learn", "--json"])

        assert first.exit_code == second.exit_code == third.exit_code == 0
        assert len(json.loads(first.output)) == len(json.loads(second.output)) == 1
        scenarios = load_scenarios(scenarios_path).scenarios
        assert len(scenarios) == 1
        assert scenarios[0].sample_count == 2
        assert {item.interaction_id for item in scenarios[0].provenance} == {"obs-1", "obs-2"}

    def test_repeated_promotion_is_idempotent(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction(), path=db_path)
        learned = runner.invoke(app, ["learn", "--json"])
        scenario_id = json.loads(learned.output)[0]["id"]

        first = runner.invoke(app, ["promote", scenario_id])
        first_content = scenarios_path.read_text(encoding="utf-8")
        second = runner.invoke(app, ["promote", scenario_id])

        assert first.exit_code == second.exit_code == 0
        assert "Promoted 0 scenario(s)" in second.output
        assert scenarios_path.read_text(encoding="utf-8") == first_content
        assert len(load_scenarios(scenarios_path).scenarios) == 1

    def test_existing_committed_scenarios_are_preserved(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        observation = _interaction()
        existing = discover_scenarios([observation])[0]
        existing.status = "promoted"
        existing.assertions = [Assertion(type="contains", value="approved")]
        unrelated = Scenario(
            id="existing_manual",
            input="Keep this scenario",
            source="manual",
            status="promoted",
            assertions=[Assertion(type="contains", value="kept")],
        )
        save_scenarios(ScenarioLibrary(scenarios=[existing, unrelated]), scenarios_path)
        before = load_scenarios(scenarios_path).model_dump(mode="json")
        before_content = scenarios_path.read_text(encoding="utf-8")
        record_interaction(observation, path=db_path)

        learned = runner.invoke(app, ["learn", "--json"])
        promoted = runner.invoke(app, ["promote", existing.id])

        assert learned.exit_code == promoted.exit_code == 0
        assert load_scenarios(scenarios_path).model_dump(mode="json") == before
        assert scenarios_path.read_text(encoding="utf-8") == before_content

    def test_empty_historical_storage_is_safe(self, tmp_path, monkeypatch):
        _, scenarios_path = _learn(monkeypatch, tmp_path)

        result = runner.invoke(app, ["learn"])

        assert result.exit_code == 0
        assert "No captured interactions found" in result.output
        assert not scenarios_path.exists()

    def test_valid_and_invalid_records_fail_as_a_batch(self, tmp_path, monkeypatch):
        db_path, scenarios_path = _learn(monkeypatch, tmp_path)
        record_interaction(_interaction("valid-observation"), path=db_path)
        record_interaction(
            _interaction("invalid-observation", timestamp=datetime(2026, 1, 2, tzinfo=UTC)),
            path=db_path,
        )
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE interactions SET model = NULL WHERE id = 'invalid-observation'")

        result = runner.invoke(app, ["learn", "--json"])

        assert result.exit_code == 2
        assert "invalid-observation" in result.output
        assert not scenarios_path.exists()
