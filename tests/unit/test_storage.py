"""Tests for SQLite local history storage."""

import sqlite3

import pytest

from promptdrift.errors import PromptDriftError
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


class TestSqliteStorageRetention:
    def test_retention_keeps_latest_runs(self, tmp_path):
        db_path = tmp_path / "test.db"

        for i in range(5):
            report = make_report()
            report.model = f"model-{i}"

            record_report(
                report,
                path=db_path,
                retention_limit=3,
            )

        with sqlite3.connect(db_path) as db:
            rows = db.execute("SELECT model FROM runs ORDER BY rowid DESC").fetchall()

        assert len(rows) == 3
        assert rows[0][0] == "model-4"
        assert rows[1][0] == "model-3"
        assert rows[2][0] == "model-2"

    def test_retention_limit_one(self, tmp_path):
        db_path = tmp_path / "test.db"

        for i in range(3):
            report = make_report()
            report.model = f"model-{i}"

            record_report(
                report,
                path=db_path,
                retention_limit=1,
            )

        with sqlite3.connect(db_path) as db:
            rows = db.execute("SELECT model FROM runs ORDER BY rowid DESC LIMIT 1").fetchall()

        assert len(rows) == 1
        assert rows[0][0] == "model-2"

    def test_invalid_retention_limit(self, tmp_path):
        with pytest.raises(ValueError):
            record_report(
                make_report(),
                path=tmp_path / "test.db",
                retention_limit=0,
            )


class TestSqliteStorageRecovery:
    def test_locked_database_error(self, tmp_path):
        from promptdrift.storage.history import SqliteStorage

        storage = SqliteStorage(str(tmp_path / "test.db"))

        with pytest.raises(PromptDriftError, match="locked"):
            storage._handle_sqlite_error(sqlite3.OperationalError("database is locked"))

    def test_corrupted_database_error(self, tmp_path):
        from promptdrift.storage.history import SqliteStorage

        storage = SqliteStorage(str(tmp_path / "test.db"))

        with pytest.raises(PromptDriftError, match="corrupted"):
            storage._handle_sqlite_error(sqlite3.DatabaseError("database disk image is malformed"))

    def test_corrupted_database_file(self, tmp_path):
        from promptdrift.storage.history import SqliteStorage

        db_path = tmp_path / "corrupted.db"
        db_path.write_text("this is not a valid sqlite database")

        storage = SqliteStorage(str(db_path))

        with pytest.raises(PromptDriftError):
            storage.get_history()

    def test_read_missing_database(self, tmp_path):
        from promptdrift.storage.history import SqliteStorage

        db_path = tmp_path / "missing.db"

        storage = SqliteStorage(str(db_path))

        assert storage.get_history() == []
        assert not db_path.exists()
