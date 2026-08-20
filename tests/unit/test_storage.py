"""Tests for SQLite local history storage."""
import sqlite3

from promptdrift.models import RegressionReport, TestRun
from promptdrift.storage import record_report


def make_report():
    return RegressionReport(
        provider="mock",
        model="test-model",
        tests=[
            TestRun(
                test_id="hello",
                provider="mock",
                model="test-model",
                input="secret prompt",
                output="secret output",
                latency_ms=10.0,
            )
        ],
    )


class TestSqliteStorage:
    def test_creates_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path)
        assert db_path.is_file()

    def test_inserts_run_record(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path)
        with sqlite3.connect(db_path) as db:
            rows = db.execute("SELECT COUNT(*) FROM runs").fetchone()
        assert rows[0] == 1

    def test_suppresses_raw_output_by_default(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path)
        with sqlite3.connect(db_path) as db:
            report_json = db.execute("SELECT report_json FROM runs").fetchone()[0]
        assert "secret prompt" not in report_json
        assert "secret output" not in report_json
        assert "[suppressed]" in report_json

    def test_stores_raw_output_when_enabled(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path, store_raw_output=True)
        with sqlite3.connect(db_path) as db:
            report_json = db.execute("SELECT report_json FROM runs").fetchone()[0]
        assert "secret prompt" in report_json
        assert "secret output" in report_json

    def test_stores_provider_and_model(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path)
        with sqlite3.connect(db_path) as db:
            row = db.execute("SELECT provider, model FROM runs").fetchone()
        assert row == ("mock", "test-model")

    def test_multiple_records(self, tmp_path):
        db_path = tmp_path / "test.db"
        record_report(make_report(), path=db_path)
        record_report(make_report(), path=db_path)
        with sqlite3.connect(db_path) as db:
            count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert count == 2

    def test_silently_handles_errors(self, tmp_path):
        # Writing to a directory path should fail silently
        record_report(make_report(), path=tmp_path)
        # No exception raised
