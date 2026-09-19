"""Rich terminal, text, and data presentations for Impact Radius Reports."""

from __future__ import annotations

from rich.console import Console

from promptdrift.impact import ImpactRadiusReport


def print_impact_report(report: ImpactRadiusReport, console: Console | None = None) -> None:
    console = console or Console()

    console.print("\n[bold]PromptDrift Impact Report[/bold]")
    console.print(
        f"Behavior changed in {report.regressed + report.improved + report.changed_but_valid} / {report.total_scenarios} scenarios."
    )
    console.print()

    console.print(f"  [green]✓ {report.improved} improved[/green]")
    console.print(f"  [cyan]⚪ {report.unchanged} unchanged[/cyan]")
    console.print(f"  [yellow]💬 {report.changed_but_valid} changed but valid[/yellow]")
    if report.regressed > 0:
        console.print(f"  [red]✗ {report.regressed} regressed[/red]")
    if report.new_scenarios > 0:
        console.print(f"  [blue]+ {report.new_scenarios} new[/blue]")
    if report.missing_scenarios > 0:
        console.print(f"  [magenta]- {report.missing_scenarios} missing[/magenta]")
    if report.not_evaluated > 0:
        console.print(
            f"  [dim]⏭ {report.not_evaluated} not evaluated (unaffected by this change)[/dim]"
        )

    console.print()
    console.print(f"[bold]Impact radius:[/] {report.impact_radius_percentage}%")
    console.print(f"Latency change: {report.latency_pct_change:+.1f}%")
    console.print(f"Cost change:    {report.cost_pct_change:+.1f}%")
    console.print()

    if report.category_breakdown:
        console.print("[bold]Affected Categories:[/bold]")
        for cat, count in report.category_breakdown.items():
            console.print(f"  {cat.capitalize():<16} {count} affected")
        console.print()

    regressions = [s for s in report.scenarios if s.classification == "REGRESSED"]
    if regressions:
        console.print("[bold red]Regressions:[/bold red]")
        for s in regressions:
            console.print(f"  [red]✗ {s.scenario_id}[/red]")
            console.print(f"    {s.details}")
        console.print()

    changed_valid = [s for s in report.scenarios if s.classification == "CHANGED_BUT_VALID"]
    if changed_valid:
        console.print(
            f"[bold yellow]Changed but valid:[/] {len(changed_valid)} scenarios changed wording while passing contracts."
        )
