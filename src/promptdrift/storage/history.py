"""Bounded, project-local monitoring history.

Never stores provider payloads.
Supports configurable retention, atomic pruning,
read-only history access, and graceful SQLite recovery.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from promptdrift.errors import PromptDriftError
from promptdrift.models.monitor import MonitorReport

HISTORY_SCHEMA_VERSION = 1
DEFAULT_RETENTION_RUNS = 1000


def history_path(config_path: Path) -> Path:
    """Return the project-local monitoring history database path."""
    return config_path.parent / ".promptdrift" / "history.sqlite3"


# ---------------------------------------------------------------------
# HISTORY SCHEMA
# ---------------------------------------------------------------------


def _validate_history_schema(db: sqlite3.Connection) -> int:
    """Validate the monitoring history database schema."""

    version = db.execute("PRAGMA user_version").fetchone()[0]

    if version > HISTORY_SCHEMA_VERSION:
        raise PromptDriftError(
            "Monitoring history schema is newer than this PromptDrift "
            "version; back up or remove the local history database."
        )

    table = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'monitor_runs'
        """
    ).fetchone()

    if table is None:
        raise PromptDriftError(
            "Monitoring history schema is incompatible; "
            "back up or remove the local history database."
        )

    columns = [row[1] for row in db.execute("PRAGMA table_info(monitor_runs)").fetchall()]

    if columns != ["run_id", "report_json"]:
        raise PromptDriftError(
            "Monitoring history schema is incompatible; "
            "back up or remove the local history database."
        )

    return version


def _ensure_history_schema(db: sqlite3.Connection) -> None:
    """Create or upgrade the monitoring history schema."""

    version = db.execute("PRAGMA user_version").fetchone()[0]

    table = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'monitor_runs'
        """
    ).fetchone()

    if table is None:
        if version != 0:
            raise PromptDriftError(
                "Monitoring history schema is incompatible; "
                "back up or remove the local history database."
            )

        db.execute(
            """
            CREATE TABLE monitor_runs (
                run_id TEXT PRIMARY KEY,
                report_json TEXT NOT NULL
            )
            """
        )

        db.execute(f"PRAGMA user_version = {HISTORY_SCHEMA_VERSION}")
        return

    version = _validate_history_schema(db)

    if version == 0:
        db.execute(f"PRAGMA user_version = {HISTORY_SCHEMA_VERSION}")


# ---------------------------------------------------------------------
# SQLITE ERROR HANDLING
# ---------------------------------------------------------------------


def _history_write_error(exc: Exception) -> PromptDriftError:
    """Convert history write errors into actionable messages."""

    message = str(exc).lower()

    if isinstance(exc, sqlite3.OperationalError) and (
        "database is locked" in message or "database is busy" in message or "locked" in message
    ):
        return PromptDriftError(
            "Monitoring history database is locked; "
            "close other PromptDrift processes using the history "
            "database and retry."
        )

    if isinstance(exc, sqlite3.DatabaseError) and (
        "file is not a database" in message
        or "database disk image is malformed" in message
        or "malformed" in message
        or "corrupt" in message
    ):
        return PromptDriftError(
            "Monitoring history database appears corrupted; "
            "back up the database first, then remove or rename it "
            "and rerun monitoring."
        )

    return PromptDriftError(
        "Monitoring completed but local history could not be saved. "
        "Check database permissions and file accessibility."
    )


def _history_read_error(exc: Exception) -> PromptDriftError:
    """Convert history read errors into actionable messages."""

    message = str(exc).lower()

    # Handle locked or busy database
    if isinstance(exc, sqlite3.OperationalError) and (
        "database is locked" in message or "database is busy" in message or "locked" in message
    ):
        return PromptDriftError(
            "Monitoring history database is locked; "
            "close other PromptDrift processes using the database "
            "and retry."
        )

    # Handle corrupted database
    if isinstance(exc, sqlite3.DatabaseError) and (
        "file is not a database" in message
        or "database disk image is malformed" in message
        or "malformed" in message
        or "corrupt" in message
    ):
        return PromptDriftError(
            "Monitoring history database appears corrupted; "
            "back up the database first, then remove or rename it "
            "and rerun monitoring."
        )

    # Handle other database read errors
    return PromptDriftError(
        "Monitoring history is unreadable; back up or remove the local history database."
    )


# ---------------------------------------------------------------------
# MONITOR REPORT STORAGE
# ---------------------------------------------------------------------


def save_monitor_report(
    report: MonitorReport,
    path: Path,
    *,
    retention: int = DEFAULT_RETENTION_RUNS,
) -> None:
    """Save a monitoring report and prune older reports atomically."""

    if retention < 1:
        raise ValueError("retention must be positive")

    try:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with closing(sqlite3.connect(path, timeout=5)) as db:
            with db:
                _ensure_history_schema(db)

                db.execute(
                    """
                    INSERT INTO monitor_runs (run_id, report_json)
                    VALUES (?, ?)
                    """,
                    (
                        report.run_id,
                        report.model_dump_json(),
                    ),
                )

                # Keep only the latest N reports.
                # Insert and pruning happen in the same transaction.
                db.execute(
                    """
                    DELETE FROM monitor_runs
                    WHERE run_id NOT IN (
                        SELECT run_id
                        FROM monitor_runs
                        ORDER BY rowid DESC
                        LIMIT ?
                    )
                    """,
                    (retention,),
                )

    except PromptDriftError:
        raise

    except (OSError, sqlite3.Error) as exc:
        raise _history_write_error(exc) from exc


def load_monitor_history(
    path: Path,
    *,
    limit: int = 20,
) -> list[dict]:
    """Load monitoring history using a strictly read-only connection."""

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")

    if not path.exists():
        return []

    try:
        db_uri = path.resolve().as_uri() + "?mode=ro"

        with closing(
            sqlite3.connect(
                db_uri,
                uri=True,
                timeout=5,
            )
        ) as db:
            _validate_history_schema(db)

            rows = db.execute(
                """
                SELECT report_json
                FROM monitor_runs
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [json.loads(row[0]) for row in rows]

    except PromptDriftError:
        raise

    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        raise _history_read_error(exc) from exc


 feature/history-retention-hardening
# ---------------------------------------------------------------------
# SQLITE STORAGE CLASS
# ---------------------------------------------------------------------


class SqliteStorage:
    """SQLite storage with bounded monitoring history."""

    def __init__(
        self,
        db_path: str,
        retention_limit: int = 100,
    ):
        if retention_limit < 1:
            raise ValueError("retention_limit must be at least 1")

        self.db_path = str(db_path)
        self.retention_limit = retention_limit

    def _get_connection(
        self,
        read_only: bool = False,
    ) -> sqlite3.Connection:
        """Create a SQLite connection."""

        try:
            if read_only:
                db_uri = Path(self.db_path).resolve().as_uri() + "?mode=ro"

                conn = sqlite3.connect(
                    db_uri,
                    uri=True,
                    timeout=5,
                )

            else:
                Path(self.db_path).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                conn = sqlite3.connect(
                    self.db_path,
                    timeout=5,
                )

            conn.row_factory = sqlite3.Row
            return conn

        except (sqlite3.Error, OSError) as exc:
            self._handle_sqlite_error(exc)

    def _ensure_schema(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        """Initialize the runs table."""

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """
        )

    def record_run(self, run_data: dict) -> None:
        """Insert a run and prune older records atomically."""

        try:
            with closing(self._get_connection()) as conn:
                with conn:
                    self._ensure_schema(conn)

                    conn.execute(
                        """
                        INSERT INTO runs (timestamp, data)
                        VALUES (?, ?)
                        """,
                        (
                            run_data["timestamp"],
                            run_data["json_payload"],
                        ),
                    )

                    # Retain only the most recent runs.
                    conn.execute(
                        """
                        DELETE FROM runs
                        WHERE id NOT IN (
                            SELECT id
                            FROM runs
                            ORDER BY timestamp DESC, id DESC
                            LIMIT ?
                        )
                        """,
                        (self.retention_limit,),
                    )

        except (sqlite3.Error, OSError) as exc:
            self._handle_sqlite_error(exc)

        except KeyError as exc:
            raise PromptDriftError(f"Invalid monitoring run data: missing field {exc}.") from exc

    def get_history(self) -> list[dict]:
        """
        Retrieve historical monitoring runs.

        Strictly read-only.
        Does not create tables, modify SQLite data,
        or call external providers.
        """

        if not Path(self.db_path).exists():
            return []

        try:
            with closing(self._get_connection(read_only=True)) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT data
                    FROM runs
                    ORDER BY timestamp DESC, id DESC
                    """
                )

                rows = cursor.fetchall()

                return [json.loads(row["data"]) for row in rows]

        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            self._handle_sqlite_error(exc)

    def _handle_sqlite_error(
        self,
        error: Exception,
    ) -> None:
        """Handle locked, corrupted, and inaccessible databases."""

        message = str(error).lower()

        if isinstance(error, sqlite3.OperationalError) and (
            "database is locked" in message or "database is busy" in message or "locked" in message
        ):
            raise PromptDriftError(
                f"Monitoring history database is locked at "
                f"'{self.db_path}'. Close other PromptDrift processes "
                "using this database and retry."
            ) from error

        if isinstance(error, sqlite3.DatabaseError) and (
            "file is not a database" in message
            or "database disk image is malformed" in message
            or "malformed" in message
            or "corrupt" in message
        ):
            raise PromptDriftError(
                f"Monitoring history database appears corrupted: "
                f"'{self.db_path}'. Back up the database first, "
                "then rename or remove it and rerun monitoring."
            ) from error

        if isinstance(error, sqlite3.DatabaseError):
            raise PromptDriftError(
                f"Unable to access monitoring history at "
                f"'{self.db_path}'. Check database permissions, "
                "schema compatibility, and file accessibility. "
                "Back up the database before recovery."
            ) from error

        raise PromptDriftError(
            f"Monitoring history operation failed at "
            f"'{self.db_path}': {error}. "
            "Check database access and retry."
        ) from error

def load_monitor_run_by_id(path: Path, run_id: str) -> MonitorReport:
    """Retrieve a specific monitoring report by its run_id."""
    if not path.exists():
        raise PromptDriftError(f"Monitoring history database not found: {path}")
    try:
        with closing(
            sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        ) as db:
            _validate_history_schema(db)
            row = db.execute(
                "SELECT report_json FROM monitor_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise PromptDriftError(f"Monitoring run '{run_id}' not found in history.")
        data = json.loads(row[0])
        if not isinstance(data, dict):
            raise PromptDriftError(
                f"Monitoring run '{run_id}' is corrupted; back up the database, "
                "then remove the run or the database."
            )
        data.pop("counts", None)
        data.pop("diagnosis_counts", None)
        return MonitorReport.model_validate(data)
    except (OSError, sqlite3.Error, ValueError) as exc:
        if isinstance(exc, PromptDriftError):
            raise
        raise _history_read_error(exc) from exc
 main
