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


class TestHistoryWALAndBusyTimeout:
    def test_writable_connection_enables_wal_and_busy_timeout(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection

        db_path = tmp_path / "history.sqlite3"
        conn = _get_history_connection(db_path, read_only=False, busy_timeout_ms=7500)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert mode.lower() == "wal"
            assert timeout == 7500
        finally:
            conn.close()

    def test_reopening_existing_wal_database(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection

        db_path = tmp_path / "history.sqlite3"
        conn1 = _get_history_connection(db_path, read_only=False, busy_timeout_ms=5000)
        conn1.execute("CREATE TABLE t (id INT)")
        conn1.commit()
        conn1.close()

        conn2 = _get_history_connection(db_path, read_only=False, busy_timeout_ms=3000)
        try:
            mode = conn2.execute("PRAGMA journal_mode").fetchone()[0]
            timeout = conn2.execute("PRAGMA busy_timeout").fetchone()[0]
            assert mode.lower() == "wal"
            assert timeout == 3000
        finally:
            conn2.close()

    def test_rejects_negative_busy_timeout(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection

        db_path = tmp_path / "history.sqlite3"
        with pytest.raises(ValueError, match="non-negative"):
            _get_history_connection(db_path, busy_timeout_ms=-1)

    def test_zero_busy_timeout_accepted(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection

        db_path = tmp_path / "history.sqlite3"
        conn = _get_history_connection(db_path, busy_timeout_ms=0)
        try:
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout == 0
        finally:
            conn.close()


def make_monitor_report(run_id="run-1"):
    from promptdrift.models.monitor import MonitorReport

    return MonitorReport(
        run_id=run_id,
        provider="mock",
        model="test-model",
        samples=1,
        baseline_path="promptdrift.baseline.json",
        tests=[],
    )


class TestHistoryReadOnly:
    def test_read_only_connection_does_not_modify_journal_mode(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection

        db_path = tmp_path / "history.sqlite3"
        init_conn = sqlite3.connect(db_path)
        init_conn.execute("PRAGMA journal_mode = DELETE")
        init_conn.execute(
            "CREATE TABLE monitor_runs (run_id TEXT PRIMARY KEY, report_json TEXT NOT NULL)"
        )
        init_conn.execute("PRAGMA user_version = 1")
        init_conn.commit()
        init_conn.close()

        ro_conn = _get_history_connection(db_path, read_only=True)
        try:
            mode = ro_conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "delete"
        finally:
            ro_conn.close()

    def test_read_only_reads_existing_wal_database(self, tmp_path):
        from promptdrift.storage.history import load_monitor_history, save_monitor_report

        db_path = tmp_path / "history.sqlite3"
        report = make_monitor_report("run-wal-1")
        save_monitor_report(report, db_path, busy_timeout_ms=5000)

        history = load_monitor_history(db_path, busy_timeout_ms=5000)
        assert len(history) == 1
        assert history[0]["run_id"] == "run-wal-1"

    def test_read_only_does_not_modify_database_state(self, tmp_path):
        from promptdrift.storage.history import _get_history_connection, save_monitor_report

        db_path = tmp_path / "history.sqlite3"
        report = make_monitor_report("run-wal-2")
        save_monitor_report(report, db_path)

        ro_conn = _get_history_connection(db_path, read_only=True)
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                ro_conn.execute("INSERT INTO monitor_runs VALUES ('bad', '{}')")
        finally:
            ro_conn.close()


class TestHistoryConcurrency:
    def test_scenario_a_concurrent_readers_and_writers(self, tmp_path):
        """Scenario A: WAL allows concurrent reader to read while writer holds transaction."""
        from promptdrift.storage.history import (
            _get_history_connection,
            load_monitor_history,
            save_monitor_report,
        )

        db_path = tmp_path / "history.sqlite3"
        report1 = make_monitor_report("run-initial")
        save_monitor_report(report1, db_path)

        writer_conn = _get_history_connection(db_path, read_only=False, busy_timeout_ms=5000)
        try:
            writer_conn.execute("BEGIN IMMEDIATE")
            writer_conn.execute(
                "INSERT INTO monitor_runs (run_id, report_json) VALUES (?, ?)",
                ("run-uncommitted", '{"run_id": "run-uncommitted"}'),
            )

            history = load_monitor_history(db_path, busy_timeout_ms=5000)
            assert [r["run_id"] for r in history] == ["run-initial"]

            writer_conn.commit()

            history_after = load_monitor_history(db_path, busy_timeout_ms=5000)
            assert "run-uncommitted" in [r["run_id"] for r in history_after]
        finally:
            writer_conn.close()

    def test_scenario_b_transient_write_lock(self, tmp_path):
        """Scenario B: Transient write lock released within timeout allows write to succeed."""
        import threading
        import time

        from promptdrift.storage.history import (
            load_monitor_history,
            save_monitor_report,
        )

        db_path = tmp_path / "history.sqlite3"
        report0 = make_monitor_report("run-0")
        save_monitor_report(report0, db_path)

        lock_acquired = threading.Event()
        thread_errors: list[Exception] = []

        def hold_lock_briefly():
            try:
                conn = sqlite3.connect(db_path, timeout=5)
                try:
                    conn.execute("PRAGMA busy_timeout = 5000")
                    conn.execute("BEGIN IMMEDIATE")
                    lock_acquired.set()
                    time.sleep(0.2)
                    conn.commit()
                finally:
                    conn.close()
            except Exception as exc:
                thread_errors.append(exc)
                lock_acquired.set()

        thread = threading.Thread(target=hold_lock_briefly)
        thread.start()
        try:
            assert lock_acquired.wait(timeout=5.0), "Lock was not acquired in time"
            assert not thread_errors, f"Error in locking thread: {thread_errors}"

            report1 = make_monitor_report("run-transient")
            save_monitor_report(report1, db_path, busy_timeout_ms=3000)
        finally:
            thread.join(timeout=5.0)

        assert not thread.is_alive(), "Worker thread did not terminate in time"
        assert not thread_errors, f"Error in locking thread: {thread_errors}"

        history = load_monitor_history(db_path)
        assert any(r["run_id"] == "run-transient" for r in history)

    def test_scenario_c_persistent_write_lock(self, tmp_path):
        """Scenario C: Persistent write lock beyond timeout raises actionable PromptDriftError."""
        from promptdrift.storage.history import save_monitor_report

        db_path = tmp_path / "history.sqlite3"
        report0 = make_monitor_report("run-0")
        save_monitor_report(report0, db_path)

        blocker_conn = sqlite3.connect(db_path, timeout=5)
        try:
            blocker_conn.execute("BEGIN IMMEDIATE")
            report1 = make_monitor_report("run-blocked")
            with pytest.raises(PromptDriftError, match="locked"):
                save_monitor_report(report1, db_path, busy_timeout_ms=100)
        finally:
            try:
                blocker_conn.rollback()
            except Exception:
                pass
            blocker_conn.close()

    def test_scenario_d_independent_database_connections(self, tmp_path):
        """Scenario D: Multiple independent threads use their own connections safely."""
        import threading

        from promptdrift.storage.history import load_monitor_history, save_monitor_report

        db_path = tmp_path / "history.sqlite3"
        report0 = make_monitor_report("run-0")
        save_monitor_report(report0, db_path)

        errors = []

        def worker_task(worker_id):
            try:
                rep = make_monitor_report(f"run-worker-{worker_id}")
                save_monitor_report(rep, db_path, busy_timeout_ms=5000)
                hist = load_monitor_history(db_path, busy_timeout_ms=5000)
                assert len(hist) >= 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        for t in threads:
            assert not t.is_alive(), "Worker thread timed out and did not terminate"

        assert not errors, f"Errors in concurrent workers: {errors}"
        history = load_monitor_history(db_path, limit=100)
        assert len(history) == 6
