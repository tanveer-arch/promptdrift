"""Rich terminal presentation."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from promptdrift.models import RegressionReport


def print_report(report: RegressionReport, console: Console | None = None) -> None:
    console = console or Console()
    counts = report.counts
    table = Table(title="PromptDrift", show_header=True)
    table.add_column("Test")
    table.add_column("Status")
    table.add_column("Reason")
    symbols = {"PASS": "[green]PASS[/]", "WARN": "[yellow]WARN[/]", "FAIL": "[red]FAIL[/]"}
    for test in report.tests:
        failed = next((item for item in test.evaluations if not item.passed), None)
        reason = failed.reason if failed else "All assertions passed"
        table.add_row(test.test_id, symbols[test.status], reason)
    console.print(table)
    console.print(f"{counts['PASS']} passed - {counts['WARN']} warnings - {counts['FAIL']} failed")
