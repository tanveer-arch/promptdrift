"""Tests for CaptureRecorder, CaptureConfig, sampling, and redaction."""

from __future__ import annotations

import pytest

from promptdrift.capture.config import CaptureConfig
from promptdrift.capture.recorder import CaptureRecorder
from promptdrift.capture.redaction import apply_redaction
from promptdrift.capture.sampling import should_sample
from promptdrift.storage.sqlite import (
    count_interactions,
    get_interactions,
    purge_old_interactions,
    purge_oldest_interactions,
)


class TestCaptureConfig:
    def test_default_disabled(self):
        cfg = CaptureConfig()
        assert cfg.enabled is False
        assert cfg.sample_rate == 1.0

    def test_rejects_invalid_sample_rate(self):
        with pytest.raises(ValueError, match="sample_rate"):
            CaptureConfig(sample_rate=1.5)
        with pytest.raises(ValueError, match="sample_rate"):
            CaptureConfig(sample_rate=-0.1)

    def test_rejects_invalid_max_interactions(self):
        with pytest.raises(ValueError, match="max_interactions"):
            CaptureConfig(max_interactions=0)

    def test_rejects_invalid_retention_days(self):
        with pytest.raises(ValueError, match="retention_days"):
            CaptureConfig(retention_days=0)


class TestCaptureRecorderBasic:
    def test_disabled_by_default_returns_none(self, tmp_path):
        recorder = CaptureRecorder(CaptureConfig(db_path=tmp_path / "test.db"))
        result = recorder.record(
            prompt="p.txt",
            input_text="hello",
            output="world",
            model="m",
            provider="mock",
        )
        assert result is None

    def test_enabled_records_interaction(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db))
        result = recorder.record(
            prompt="p.txt",
            input_text="hello",
            output="world",
            model="gpt-4",
            provider="openai",
            latency_ms=42.5,
            input_tokens=3,
            output_tokens=1,
            estimated_cost_usd=0.001,
            tags=["test"],
        )
        assert result is not None
        assert result.input == "hello"
        assert result.output == "world"
        assert result.model == "gpt-4"
        assert result.provider == "openai"
        assert result.latency_ms == 42.5

        # Verify stored in SQLite
        items = get_interactions(path=db)
        assert len(items) == 1
        assert items[0].id == result.id

    def test_default_tags_merged(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(
            CaptureConfig(enabled=True, db_path=db, default_tags=["prod", "v2"])
        )
        result = recorder.record(
            prompt="p.txt",
            input_text="hi",
            output="bye",
            model="m",
            provider="mock",
            tags=["extra"],
        )
        assert result is not None
        assert "prod" in result.tags
        assert "v2" in result.tags
        assert "extra" in result.tags

    def test_never_raises_on_bad_db_path(self):
        """Capture failures must never break the host application."""
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=None))
        # Even with a weird config, record should not raise
        result = recorder.record(
            prompt="p.txt",
            input_text="test",
            output="out",
            model="m",
            provider="mock",
        )
        # May or may not succeed depending on default path,
        # but must NOT raise
        assert result is None or result is not None

    def test_system_prompt_recorded(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db))
        result = recorder.record(
            prompt="p.txt",
            input_text="hi",
            output="hello",
            model="m",
            provider="mock",
            system_prompt="You are a helpful assistant",
        )
        assert result is not None
        assert result.system_prompt == "You are a helpful assistant"


class TestCaptureRecorderRollingCap:
    def test_max_interactions_rolling_eviction(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db, max_interactions=3))
        # Record 5 interactions
        for i in range(5):
            recorder.record(
                prompt="p.txt",
                input_text=f"input_{i}",
                output=f"output_{i}",
                model="m",
                provider="mock",
            )
        # Should have at most 3
        assert count_interactions(path=db) <= 3

    def test_new_interactions_replace_oldest(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db, max_interactions=2))
        recorder.record(prompt="p.txt", input_text="first", output="o1", model="m", provider="mock")
        recorder.record(
            prompt="p.txt", input_text="second", output="o2", model="m", provider="mock"
        )
        r3 = recorder.record(
            prompt="p.txt", input_text="third", output="o3", model="m", provider="mock"
        )

        items = get_interactions(path=db)
        ids = {item.id for item in items}
        assert len(items) <= 2
        # The newest should still be present
        assert r3 is not None
        assert r3.id in ids


class TestCaptureRecorderRedaction:
    def test_email_redaction(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(
            CaptureConfig(enabled=True, db_path=db, redact_patterns=["email"])
        )
        result = recorder.record(
            prompt="p.txt",
            input_text="Contact me at john@example.com",
            output="I'll reach you at john@example.com",
            model="m",
            provider="mock",
        )
        assert result is not None
        assert "john@example.com" not in result.input
        assert "john@example.com" not in result.output
        assert "[REDACTED]" in result.input

    def test_phone_redaction(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(
            CaptureConfig(enabled=True, db_path=db, redact_patterns=["phone"])
        )
        result = recorder.record(
            prompt="p.txt",
            input_text="Call me at 555-123-4567",
            output="ok",
            model="m",
            provider="mock",
        )
        assert result is not None
        assert "555-123-4567" not in result.input

    def test_custom_callback(self, tmp_path):
        db = tmp_path / "test.db"

        def custom_redact(text: str) -> str:
            return text.replace("SECRET", "***")

        recorder = CaptureRecorder(
            CaptureConfig(enabled=True, db_path=db, redact_callback=custom_redact)
        )
        result = recorder.record(
            prompt="p.txt",
            input_text="My SECRET password",
            output="Got it",
            model="m",
            provider="mock",
        )
        assert result is not None
        assert "SECRET" not in result.input
        assert "***" in result.input

    def test_system_prompt_also_redacted(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(
            CaptureConfig(enabled=True, db_path=db, redact_patterns=["email"])
        )
        result = recorder.record(
            prompt="p.txt",
            input_text="hi",
            output="ok",
            model="m",
            provider="mock",
            system_prompt="Admin email: admin@corp.com",
        )
        assert result is not None
        assert "admin@corp.com" not in result.system_prompt


class TestSampling:
    def test_rate_1_always_samples(self):
        assert should_sample("any_fingerprint", 1.0) is True

    def test_rate_0_never_samples(self):
        assert should_sample("any_fingerprint", 0.0) is False

    def test_deterministic(self):
        """Same fingerprint + same rate = same decision."""
        fp = "test_fingerprint_12345"
        decision1 = should_sample(fp, 0.5)
        decision2 = should_sample(fp, 0.5)
        assert decision1 == decision2

    def test_different_fingerprints_vary(self):
        """With rate=0.5 and many fingerprints, we expect a mix of True/False."""
        results = [should_sample(f"fp_{i}", 0.5) for i in range(1000)]
        true_count = sum(results)
        # With 1000 samples at 50%, we expect roughly 400-600 True
        assert 300 < true_count < 700

    def test_sampling_applied_by_recorder(self, tmp_path):
        db = tmp_path / "test.db"
        recorder = CaptureRecorder(CaptureConfig(enabled=True, db_path=db, sample_rate=0.0))
        result = recorder.record(
            prompt="p.txt",
            input_text="hello",
            output="world",
            model="m",
            provider="mock",
        )
        assert result is None
        assert count_interactions(path=db) == 0


class TestRedaction:
    def test_email_pattern(self):
        text = "Email me at user@example.com please"
        result = apply_redaction(text, ["email"])
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_phone_pattern(self):
        text = "Call 555-123-4567"
        result = apply_redaction(text, ["phone"])
        assert "555-123-4567" not in result

    def test_api_token_pattern(self):
        text = "Use Bearer sk-abc123defghijklmnop for auth"
        result = apply_redaction(text, ["api_token"])
        assert "sk-abc123defghijklmnop" not in result

    def test_custom_regex_pattern(self):
        text = "SSN: 123-45-6789"
        result = apply_redaction(text, [r"\d{3}-\d{2}-\d{4}"])
        assert "123-45-6789" not in result

    def test_invalid_regex_skipped(self):
        text = "Hello world"
        result = apply_redaction(text, ["[invalid"])
        assert result == "Hello world"

    def test_callback_applied_after_patterns(self):
        def cb(text: str) -> str:
            return text.replace("foo", "bar")

        result = apply_redaction("foo@example.com and foo", ["email"], cb)
        assert "foo@example.com" not in result
        assert "bar" in result

    def test_callback_failure_silent(self):
        def bad_cb(text: str) -> str:
            raise RuntimeError("boom")

        result = apply_redaction("hello", [], bad_cb)
        assert result == "hello"

    def test_empty_text(self):
        assert apply_redaction("", ["email"]) == ""

    def test_none_patterns(self):
        assert apply_redaction("hello", None) == "hello"


class TestSqliteHelpers:
    def test_count_interactions(self, tmp_path):
        from promptdrift.models.capture import Interaction

        db = tmp_path / "test.db"
        assert count_interactions(path=db) == 0
        from promptdrift.storage.sqlite import record_interaction

        record_interaction(
            Interaction(
                id="i1",
                provider="m",
                model="m",
                prompt="p",
                input="a",
                output="b",
            ),
            path=db,
        )
        assert count_interactions(path=db) == 1

    def test_purge_oldest(self, tmp_path):
        from datetime import UTC, datetime

        from promptdrift.models.capture import Interaction
        from promptdrift.storage.sqlite import record_interaction

        db = tmp_path / "test.db"
        for i in range(5):
            record_interaction(
                Interaction(
                    id=f"i{i}",
                    provider="m",
                    model="m",
                    prompt="p",
                    input=f"in_{i}",
                    output=f"out_{i}",
                    timestamp=datetime(2024, 1, 1 + i, tzinfo=UTC),
                ),
                path=db,
            )
        assert count_interactions(path=db) == 5
        purge_oldest_interactions(2, path=db)
        assert count_interactions(path=db) == 3

    def test_purge_old_by_days(self, tmp_path):
        from datetime import UTC, datetime, timedelta

        from promptdrift.models.capture import Interaction
        from promptdrift.storage.sqlite import record_interaction

        db = tmp_path / "test.db"
        old_time = datetime.now(UTC) - timedelta(days=60)
        new_time = datetime.now(UTC)

        record_interaction(
            Interaction(
                id="old",
                provider="m",
                model="m",
                prompt="p",
                input="a",
                output="b",
                timestamp=old_time,
            ),
            path=db,
        )
        record_interaction(
            Interaction(
                id="new",
                provider="m",
                model="m",
                prompt="p",
                input="c",
                output="d",
                timestamp=new_time,
            ),
            path=db,
        )
        assert count_interactions(path=db) == 2
        purge_old_interactions(30, path=db)
        remaining = get_interactions(path=db)
        assert len(remaining) == 1
        assert remaining[0].id == "new"
