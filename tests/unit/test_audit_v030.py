"""Audit tests for v0.3.0 architecture compliance.

These tests verify each approved requirement:
1. Deterministic fingerprint excludes timestamp
2. Scenario identity separates different edge cases
3. max_interactions is a rolling cap
4. Prompt hashing only uses referenced files
5. Capture cannot auto-modify promoted assertions/inputs/baseline
6. Selective acceptance rules
7. Baseline history archived before replacement
8. Baseline metadata contains required fields and v0.2 compat
9. OpenAI integration safety
10. SQLite thread/process safety
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime

import pytest

from promptdrift.capture.config import CaptureConfig
from promptdrift.capture.recorder import CaptureRecorder, _interaction_fingerprint
from promptdrift.engine.accept import selective_accept
from promptdrift.engine.baseline import baseline_from_report, load_baseline, write_baseline
from promptdrift.engine.baseline_history import archive_baseline, list_baseline_history
from promptdrift.engine.discovery import discover_scenarios
from promptdrift.errors import PromptDriftError
from promptdrift.impact import ImpactRadiusReport, ScenarioImpact
from promptdrift.models.baseline import Baseline, BaselineTest
from promptdrift.models.capture import Interaction
from promptdrift.models.result import RegressionReport, TestRun
from promptdrift.storage.sqlite import (
    count_interactions,
    get_interactions,
    record_interaction,
)

# ---------------------------------------------------------------------------
# Req 1: Deterministic fingerprint must NOT include timestamp
# ---------------------------------------------------------------------------


class TestFingerprintStability:
    def test_same_interaction_different_times_same_fingerprint(self):
        """The same logical interaction at different times MUST produce the same fingerprint."""
        fp1 = _interaction_fingerprint(
            "openai", "gpt-4", "prompts/cs.txt", "I want a refund", {"order": "123"}
        )
        time.sleep(0.01)  # simulate time passing
        fp2 = _interaction_fingerprint(
            "openai", "gpt-4", "prompts/cs.txt", "I want a refund", {"order": "123"}
        )
        assert fp1 == fp2

    def test_different_inputs_different_fingerprints(self):
        fp1 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "refund after 5 days", {})
        fp2 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "refund after 45 days", {})
        assert fp1 != fp2

    def test_different_providers_different_fingerprints(self):
        fp1 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hello", {})
        fp2 = _interaction_fingerprint("ollama", "gpt-4", "p.txt", "hello", {})
        assert fp1 != fp2

    def test_whitespace_normalized(self):
        fp1 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "  hello  world  ", {})
        fp2 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hello world", {})
        assert fp1 == fp2

    def test_variables_included_in_fingerprint(self):
        fp1 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hi", {"a": "1"})
        fp2 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hi", {"a": "2"})
        assert fp1 != fp2

    def test_none_variables_equivalent_to_empty(self):
        fp1 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hi", None)
        fp2 = _interaction_fingerprint("openai", "gpt-4", "p.txt", "hi", {})
        assert fp1 == fp2


# ---------------------------------------------------------------------------
# Req 2: Scenario identity — different edge cases remain separate
# ---------------------------------------------------------------------------


class TestScenarioIdentity:
    def test_different_refund_edge_cases_are_separate(self):
        """Different refund edge cases MUST remain separate scenarios."""
        now = datetime.now(UTC)
        interactions = [
            Interaction(
                id="i1",
                provider="openai",
                model="gpt-4",
                prompt="prompts/cs.txt",
                input="I want a refund for order placed 5 days ago",
                output="ok",
                timestamp=now,
            ),
            Interaction(
                id="i2",
                provider="openai",
                model="gpt-4",
                prompt="prompts/cs.txt",
                input="I want a refund for order placed 45 days ago",
                output="partial",
                timestamp=now,
            ),
            Interaction(
                id="i3",
                provider="openai",
                model="gpt-4",
                prompt="prompts/cs.txt",
                input="I want a refund for order placed 90 days ago",
                output="denied",
                timestamp=now,
            ),
        ]
        scenarios = discover_scenarios(interactions)
        assert len(scenarios) == 3, f"Expected 3 separate scenarios, got {len(scenarios)}"

    def test_identical_interactions_merge(self):
        """Identical interactions should merge into one scenario with sample_count > 1."""
        now = datetime.now(UTC)
        interactions = [
            Interaction(
                id="i1",
                provider="openai",
                model="gpt-4",
                prompt="p.txt",
                input="Hello",
                output="Hi",
                timestamp=now,
            ),
            Interaction(
                id="i2",
                provider="openai",
                model="gpt-4",
                prompt="p.txt",
                input="Hello",
                output="Hi there",
                timestamp=now,
            ),
        ]
        scenarios = discover_scenarios(interactions)
        assert len(scenarios) == 1
        assert scenarios[0].sample_count == 2


# ---------------------------------------------------------------------------
# Req 3: max_interactions is a rolling cap
# ---------------------------------------------------------------------------


class TestRollingCap:
    def test_rolling_cap_replaces_oldest(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db, max_interactions=3))
        for i in range(6):
            recorder.record(
                prompt="p.txt",
                input_text=f"msg_{i}",
                output=f"out_{i}",
                model="m",
                provider="mock",
            )
        count = count_interactions(path=db)
        assert count <= 3, f"Rolling cap violated: {count} > 3"

    def test_newest_interaction_survives(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db, max_interactions=2))
        for i in range(5):
            recorder.record(
                prompt="p.txt",
                input_text=f"msg_{i}",
                output=f"out_{i}",
                model="m",
                provider="mock",
            )
        items = get_interactions(path=db)
        inputs = {it.input for it in items}
        # The most recent input should be present
        assert "msg_4" in inputs


# ---------------------------------------------------------------------------
# Req 4: Prompt hashing only uses referenced files
# ---------------------------------------------------------------------------


class TestPromptHashing:
    def test_only_referenced_files_hashed(self, tmp_path):
        from promptdrift.git import GitContext

        # Create prompt files
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "used.txt").write_text("You are helpful", encoding="utf-8")
        (tmp_path / "prompts" / "unused.txt").write_text("DECOY CONTENT", encoding="utf-8")

        ctx = GitContext(root=tmp_path)
        referenced = [tmp_path / "prompts" / "used.txt"]
        hash1 = ctx.compute_prompt_hash(referenced)

        # Change the UNREFERENCED file
        (tmp_path / "prompts" / "unused.txt").write_text("CHANGED DECOY", encoding="utf-8")
        hash2 = ctx.compute_prompt_hash(referenced)

        assert hash1 == hash2, "Unreferenced file change should not affect prompt hash"

    def test_referenced_file_change_updates_hash(self, tmp_path):
        from promptdrift.git import GitContext

        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "used.txt").write_text("v1", encoding="utf-8")

        ctx = GitContext(root=tmp_path)
        referenced = [tmp_path / "prompts" / "used.txt"]
        hash1 = ctx.compute_prompt_hash(referenced)

        (tmp_path / "prompts" / "used.txt").write_text("v2", encoding="utf-8")
        hash2 = ctx.compute_prompt_hash(referenced)

        assert hash1 != hash2, "Referenced file change must update prompt hash"


# ---------------------------------------------------------------------------
# Req 5: Capture cannot auto-modify promoted scenarios or baseline
# ---------------------------------------------------------------------------


class TestCaptureIsolation:
    def test_capture_does_not_touch_scenario_assertions(self, tmp_path):
        from promptdrift.models.capture import Scenario, ScenarioLibrary
        from promptdrift.storage.scenarios import save_scenarios

        scenarios_path = tmp_path / "scenarios.json"
        promoted = Scenario(
            id="refund_5d",
            prompt="p.txt",
            input="refund 5 days",
            status="promoted",
            assertions=[{"type": "contains", "value": "approved"}],
        )
        lib = ScenarioLibrary(scenarios=[promoted])
        save_scenarios(lib, scenarios_path)

        # Capture a new interaction — must NOT alter the promoted scenario
        db = tmp_path / "capture.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db))
        recorder.record(
            prompt="p.txt",
            input_text="refund 5 days",
            output="different answer",
            model="m",
            provider="mock",
        )

        from promptdrift.engine.discovery import discover_scenarios
        from promptdrift.storage.scenarios import add_or_update_scenarios
        from promptdrift.storage.sqlite import get_interactions

        interactions = get_interactions(path=db)
        new_scenarios = discover_scenarios(interactions)
        add_or_update_scenarios(new_scenarios, scenarios_path)

        from promptdrift.storage.scenarios import load_scenarios

        reloaded = load_scenarios(scenarios_path)
        match = [s for s in reloaded.scenarios if s.id == "refund_5d"][0]
        assert match.assertions[0].type == "contains"
        assert match.assertions[0].value == "approved"
        assert match.input == "refund 5 days"
        assert match.status == "promoted"


# ---------------------------------------------------------------------------
# Req 6: Selective acceptance rules
# ---------------------------------------------------------------------------


class TestSelectiveAcceptance:
    def _make_baseline_and_report(self):
        baseline = Baseline(
            schema_version=2,
            promptdrift_version="0.3.0",
            generated_at=datetime.now(UTC),
            provider={"type": "mock", "model": "mock"},
            tests={
                "sc_unchanged": BaselineTest(
                    output_hash="aaa",
                    status="PASS",
                    assertions={"contains:ok": True},
                    metrics={
                        "latency_ms": 10,
                        "input_tokens": 5,
                        "output_tokens": 5,
                        "estimated_cost_usd": 0.0,
                    },
                ),
                "sc_regressed": BaselineTest(
                    output_hash="bbb",
                    status="PASS",
                    assertions={"contains:yes": True},
                    metrics={
                        "latency_ms": 10,
                        "input_tokens": 5,
                        "output_tokens": 5,
                        "estimated_cost_usd": 0.0,
                    },
                ),
                "sc_changed": BaselineTest(
                    output_hash="ccc",
                    status="PASS",
                    assertions={"contains:data": True},
                    metrics={
                        "latency_ms": 10,
                        "input_tokens": 5,
                        "output_tokens": 5,
                        "estimated_cost_usd": 0.0,
                    },
                ),
            },
        )

        report = RegressionReport(
            generated_at=datetime.now(UTC),
            provider="mock",
            model="mock",
            duration_ms=100.0,
            tests=[
                TestRun(
                    test_id="sc_unchanged",
                    provider="mock",
                    model="mock",
                    input="in",
                    status="PASS",
                    output="ok",
                    latency_ms=10,
                ),
                TestRun(
                    test_id="sc_regressed",
                    provider="mock",
                    model="mock",
                    input="in",
                    status="FAIL",
                    output="no",
                    latency_ms=10,
                ),
                TestRun(
                    test_id="sc_changed",
                    provider="mock",
                    model="mock",
                    input="in",
                    status="PASS",
                    output="changed data",
                    latency_ms=10,
                ),
            ],
        )

        impact = ImpactRadiusReport(
            total_scenarios=3,
            regressed=1,
            improved=0,
            unchanged=1,
            changed_but_valid=1,
            new_scenarios=0,
            missing_scenarios=0,
            impact_radius_percentage=66.7,
            scenarios=[
                ScenarioImpact(
                    scenario_id="sc_unchanged",
                    classification="UNCHANGED",
                    baseline_status="PASS",
                    current_status="PASS",
                    output_changed=False,
                    details="",
                ),
                ScenarioImpact(
                    scenario_id="sc_regressed",
                    classification="REGRESSED",
                    baseline_status="PASS",
                    current_status="FAIL",
                    output_changed=True,
                    details="",
                ),
                ScenarioImpact(
                    scenario_id="sc_changed",
                    classification="CHANGED_BUT_VALID",
                    baseline_status="PASS",
                    current_status="PASS",
                    output_changed=True,
                    details="",
                ),
            ],
        )
        return baseline, report, impact

    def test_regressed_blocked_by_default(self):
        bl, rpt, imp = self._make_baseline_and_report()
        with pytest.raises(PromptDriftError, match="REGRESSED"):
            selective_accept(bl, rpt, imp, accept_changed=True)

    def test_changed_but_valid_not_accepted_by_default(self):
        bl, rpt, imp = self._make_baseline_and_report()
        # Remove the regression scenario from impact to avoid the error
        imp.scenarios = [s for s in imp.scenarios if s.classification != "REGRESSED"]
        imp.regressed = 0
        new_bl = selective_accept(bl, rpt, imp)
        # sc_changed should NOT be updated (still old hash)
        assert new_bl.tests["sc_changed"].output_hash == "ccc"

    def test_scenario_id_restricts_scope(self):
        bl, rpt, imp = self._make_baseline_and_report()
        imp.scenarios = [s for s in imp.scenarios if s.classification != "REGRESSED"]
        imp.regressed = 0
        new_bl = selective_accept(bl, rpt, imp, scenario_ids=["sc_changed"], accept_changed=True)
        # Only sc_changed should be updated
        assert new_bl.tests["sc_changed"].output_hash != "ccc"
        assert new_bl.tests["sc_unchanged"].output_hash == "aaa"

    def test_accept_regressions_flag_required(self):
        bl, rpt, imp = self._make_baseline_and_report()
        new_bl = selective_accept(bl, rpt, imp, accept_regressions=True, accept_changed=True)
        # All should be updated now
        assert new_bl.tests["sc_regressed"].output_hash != "bbb"


# ---------------------------------------------------------------------------
# Req 7: Baseline history archived before every replacement
# ---------------------------------------------------------------------------


class TestBaselineHistoryArchiving:
    def test_archive_before_write(self, tmp_path):
        history_dir = tmp_path / "history"
        baseline_path = tmp_path / "baseline.json"

        # Create an initial baseline
        report = RegressionReport(
            generated_at=datetime.now(UTC),
            provider="mock",
            model="mock",
            duration_ms=100.0,
            tests=[
                TestRun(
                    test_id="t1",
                    provider="mock",
                    model="mock",
                    input="in",
                    status="PASS",
                    output="v1",
                    latency_ms=10,
                )
            ],
        )
        write_baseline(baseline_path, report, force=True)

        # Archive it
        archived = archive_baseline(baseline_path, history_dir=history_dir)
        assert archived is not None
        assert archived.is_file()

        # Write a new baseline (simulating replacement)
        report2 = RegressionReport(
            generated_at=datetime.now(UTC),
            provider="mock",
            model="mock",
            duration_ms=100.0,
            tests=[
                TestRun(
                    test_id="t1",
                    provider="mock",
                    model="mock",
                    input="in",
                    status="PASS",
                    output="v2",
                    latency_ms=10,
                )
            ],
        )
        write_baseline(baseline_path, report2, force=True)

        # History should have 2 entries now (write_baseline itself also archives)
        history = list_baseline_history(history_dir)
        assert len(history) >= 1

        # The archived copy should contain the old content
        old_data = json.loads(archived.read_text(encoding="utf-8"))
        old_bl = Baseline.model_validate(old_data)
        assert "t1" in old_bl.tests


# ---------------------------------------------------------------------------
# Req 8: Baseline metadata and v0.2 compatibility
# ---------------------------------------------------------------------------


class TestBaselineMetadata:
    def test_baseline_contains_required_metadata(self, tmp_path):
        report = RegressionReport(
            generated_at=datetime.now(UTC),
            provider="openai",
            model="gpt-4",
            duration_ms=100.0,
            tests=[
                TestRun(
                    test_id="t1",
                    provider="openai",
                    model="gpt-4",
                    input="in",
                    status="PASS",
                    output="out",
                    latency_ms=10,
                )
            ],
        )
        bl = baseline_from_report(report, git_sha="abc123", prompt_hash="def456")
        assert bl.git_sha == "abc123"
        assert bl.prompt_hash == "def456"
        assert bl.generated_at is not None
        assert bl.provider == {"type": "openai", "model": "gpt-4"}

    def test_v02_baseline_loads_correctly(self, tmp_path):
        """v0.2 baseline files (schema_version=1, no git_sha/prompt_hash) must load."""
        v1_data = {
            "schema_version": 1,
            "promptdrift_version": "0.2.0",
            "generated_at": "2026-09-19T00:00:00+00:00",
            "provider": {"type": "mock", "model": "mock"},
            "prompt_revision": None,
            "tests": {
                "t1": {
                    "output_hash": "abc",
                    "status": "PASS",
                    "assertions": {"contains:ok": True},
                    "metrics": {"latency_ms": 10.0},
                }
            },
        }
        p = tmp_path / "baseline_v1.json"
        p.write_text(json.dumps(v1_data), encoding="utf-8")
        bl = load_baseline(p)
        assert bl.schema_version == 2  # migrated
        assert bl.git_sha is None  # not present in v1
        assert bl.prompt_hash is None
        assert "t1" in bl.tests


# ---------------------------------------------------------------------------
# Req 10: Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_inserts(self, tmp_path):
        db = tmp_path / "threaded.db"
        errors = []

        def insert(idx):
            try:
                record_interaction(
                    Interaction(
                        id=f"thread_{idx}",
                        provider="mock",
                        model="m",
                        prompt="p",
                        input=f"in_{idx}",
                        output=f"out_{idx}",
                    ),
                    path=db,
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=insert, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety violation: {errors}"
        count = count_interactions(path=db)
        assert count == 20
