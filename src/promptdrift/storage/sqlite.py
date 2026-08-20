"""Best-effort local history. It is never required for a run."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from promptdrift.models import RegressionReport


def record_report(
    report: RegressionReport,
    path: Path | None = None,
    *,
    store_raw_output: bool = False,
) -> None:
    """Persist local history without raw prompts/outputs unless explicitly requested."""
    try:
        stored = report.model_copy(deep=True)
        if not store_raw_output:
            for test in stored.tests:
                test.input = "[suppressed]"
                test.output = "[suppressed]"
        db_path = path or (Path.home() / ".promptdrift" / "promptdrift.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (created_at TEXT, provider TEXT, model TEXT, report_json TEXT)")
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (report.generated_at.isoformat(), report.provider,
                       report.model, stored.model_dump_json()))
    except (sqlite3.Error, OSError):
        pass
