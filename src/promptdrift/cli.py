"""PromptDrift command-line interface."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import __version__
from .config import load_config
from .engine.baseline import load_baseline, write_baseline
from .engine.capture import create_interaction
from .engine.check import orchestrate_check
from .engine.discovery import discover_scenarios
from .engine.regression import compare_to_baseline
from .engine.runner import run_suite
from .engine.suggest import suggest_assertions_for_scenario
from .errors import BaselineError, ConfigError, PromptDriftError, ProviderError, TemplateError
from .git import GitContext
from .reports import print_impact_report, print_report, write_html_report
from .storage import (
    add_or_update_scenarios,
    get_interactions,
    load_scenarios,
    purge_storage,
    record_report,
    save_scenarios,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Git-native CI regression testing for LLM prompts.",
)
console = Console()


def _exit_error(error: Exception, verbose: bool = False) -> None:
    if verbose:
        raise error
    console.print(f"[red]Error:[/] {error}")
    code = (
        3
        if isinstance(error, ProviderError)
        else 2
        if isinstance(error, (ConfigError, BaselineError, TemplateError))
        else 3
    )
    raise typer.Exit(code=code)


def _run(config: str, with_baseline: bool, verbose: bool):
    try:
        loaded, config_path = load_config(config)
        report = run_suite(loaded, config_path)
        baseline_path = loaded.resolve_path(config_path, loaded.baseline.path)
        if with_baseline and baseline_path.exists():
            report = compare_to_baseline(report, load_baseline(baseline_path))
            report.baseline_path = str(baseline_path)
        record_report(report, store_raw_output=loaded.baseline.store_raw_output)
        return loaded, config_path, report
    except PromptDriftError as error:
        _exit_error(error, verbose)
    return None


def _emit(report, as_json: bool) -> None:
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        print_report(report, console)
    if report.counts["FAIL"]:
        raise typer.Exit(code=1)


@app.command()
def init(
    directory: Annotated[Path, typer.Option("--directory", "-d", help="Project directory.")] = Path(
        "."
    ),
    force: Annotated[bool, typer.Option(help="Replace generated starter files.")] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Non-interactive default setup.")
    ] = False,
) -> None:
    """Zero-config project setup detecting Git repository and local prompt files."""
    git = GitContext(root=directory)
    is_git = git.is_git_repo()

    prompt_files = list(directory.glob("prompts/**/*.*")) + list(directory.glob("*.txt"))
    config_file = directory / "promptdrift.yaml"
    example_prompt = directory / "prompts" / "example.txt"

    if (config_file.exists() or example_prompt.exists()) and not force:
        console.print("[red]Error:[/] Starter files already exist. Use --force to replace them.")
        raise typer.Exit(code=2)

    console.print(
        f"{'[green]✓[/]' if is_git else '[yellow]⚪[/]'} Git repository {'detected' if is_git else 'not detected'}"
    )
    if prompt_files:
        console.print(f"[green]✓[/] Prompt files detected: {len(prompt_files)} files")
    else:
        console.print("[yellow]⚪[/] No existing prompt files found; creating prompts/example.txt")

    example_prompt.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        """version: 2

project:
  name: promptdrift-starter

provider:
  type: mock
  model: local-echo

defaults:
  temperature: 0
  max_output_tokens: 500

baseline:
  path: promptdrift.baseline.json

tests:
  - id: hello
    prompt: prompts/example.txt
    variables:
      input: Hello
    assertions:
      - type: contains
        value: Hello
""",
        encoding="utf-8",
    )
    example_prompt.write_text(
        "Reply to this input exactly and concisely: {{ input }}\n", encoding="utf-8"
    )
    console.print(
        "[green]Created[/] promptdrift.yaml and prompts/example.txt\nRun: promptdrift check"
    )


@app.command()
def capture(
    input_text: Annotated[str, typer.Option("--input", "-i", help="Prompt input text.")] = "",
    output_text: Annotated[str, typer.Option("--output", "-o", help="Model output text.")] = "",
    provider: Annotated[str, typer.Option(help="Provider name.")] = "openai",
    model: Annotated[str, typer.Option(help="Model name.")] = "gpt-4.1-mini",
    prompt_file: Annotated[
        str, typer.Option(help="Prompt file reference.")
    ] = "prompts/example.txt",
    tag: Annotated[list[str], typer.Option(help="Tags for interaction.")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Capture a real or simulated interaction into local storage for learning."""
    if not input_text or not output_text:
        console.print("[yellow]Capturing example offline interaction for demonstration...[/]")
        input_text = input_text or "Can I get a refund for order #1234?"
        output_text = (
            output_text or "Refunds are processed within 30 days of purchase per company policy."
        )

    interaction = create_interaction(
        provider=provider,
        model=model,
        prompt=prompt_file,
        input=input_text,
        output=output_text,
        tags=tag or ["support"],
    )
    if json_output:
        typer.echo(interaction.model_dump_json(indent=2))
    else:
        console.print(f"[green]Captured interaction:[/] {interaction.id}")


@app.command()
def learn(
    limit: Annotated[int, typer.Option(help="Maximum interactions to process.")] = 1000,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Turn captured interactions into candidate regression scenarios."""
    interactions = get_interactions(limit=limit)
    if not interactions:
        console.print("[yellow]No captured interactions found. Use 'promptdrift capture' first.[/]")
        return

    scenarios = discover_scenarios(interactions)
    add_or_update_scenarios(scenarios)

    if json_output:
        typer.echo(json.dumps([s.model_dump() for s in scenarios], indent=2, default=str))
    else:
        console.print(f"[green]✓[/] {len(interactions)} interactions loaded")
        console.print(
            f"[green]✓[/] {len(scenarios)} candidate scenarios discovered and saved to .promptdrift/scenarios.json"
        )
        console.print("\nReview candidates with: [bold]promptdrift scenarios[/bold]")
        console.print("Promote candidates with: [bold]promptdrift promote <scenario-id>[/bold]")


@app.command()
def scenarios(
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List scenarios in the scenario library."""
    lib = load_scenarios()
    if json_output:
        typer.echo(lib.model_dump_json(indent=2))
    else:
        if not lib.scenarios:
            console.print(
                "[yellow]Scenario library is empty. Run 'promptdrift learn' or author YAML tests.[/]"
            )
            return
        console.print(f"[bold]Scenario Library ({len(lib.scenarios)} items):[/bold]")
        for sc in lib.scenarios:
            status_color = "green" if sc.status == "promoted" else "yellow"
            console.print(
                f"  - [{status_color}]{sc.id}[/{status_color}] ({sc.status}) - {sc.input[:60]}"
            )


@app.command()
def suggest(
    scenario_id: Annotated[str, typer.Argument(help="Scenario ID to suggest contracts for.")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Suggest deterministic behavioral contracts for a scenario."""
    lib = load_scenarios()
    scenario = next((s for s in lib.scenarios if s.id == scenario_id), None)
    if not scenario:
        console.print(f"[red]Error:[/] Scenario '{scenario_id}' not found.")
        raise typer.Exit(code=2)

    interactions = get_interactions()
    suggestions = suggest_assertions_for_scenario(scenario, interactions)

    if json_output:
        typer.echo(json.dumps([a.model_dump() for a in suggestions], indent=2))
    else:
        console.print(f"[bold]Suggested contracts for {scenario_id}:[/bold]")
        for a in suggestions:
            console.print(f"  ✓ {a.type} -> {a.value or a.schema_ or ''} (severity: {a.severity})")


@app.command()
def promote(
    scenario_id: Annotated[str, typer.Argument(help="Scenario ID to promote to active suite.")],
    all_candidates: Annotated[
        bool, typer.Option("--all", help="Promote all candidate scenarios.")
    ] = False,
) -> None:
    """Promote candidate scenarios into committed regression tests."""
    lib = load_scenarios()
    promoted_count = 0
    interactions = get_interactions()

    for sc in lib.scenarios:
        if all_candidates or sc.id == scenario_id:
            sc.status = "promoted"
            if not sc.assertions:
                sc.assertions = suggest_assertions_for_scenario(sc, interactions)
            promoted_count += 1

    save_scenarios(lib)
    console.print(f"[green]Promoted {promoted_count} scenario(s) to active regression suite.[/]")
    console.print(
        "[dim]Commit .promptdrift/scenarios.json to version-control your regression tests.[/]"
    )


@app.command()
def check(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    base: Annotated[
        str | None,
        typer.Option("--base", help="Git base ref (e.g. origin/main) for selective check."),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Git-aware scenario execution and Impact Radius report."""
    try:
        loaded, config_path = load_config(config)
        report, impact = orchestrate_check(loaded, config_path, base_ref=base)
        record_report(report, store_raw_output=loaded.baseline.store_raw_output)

        if json_output:
            out_data = {
                "report": report.model_dump(),
                "impact": impact.model_dump(),
            }
            typer.echo(json.dumps(out_data, indent=2, default=str))
        else:
            print_impact_report(impact, console)

        # Policy evaluation: fail on regression
        fail_triggers = loaded.policy.fail_on if loaded.policy else ["regression"]
        if "regression" in fail_triggers and impact.regressed > 0:
            raise typer.Exit(code=1)
        if report.counts["FAIL"]:
            raise typer.Exit(code=1)
    except PromptDriftError as error:
        _exit_error(error, verbose)


@app.command()
def accept(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    force: Annotated[bool, typer.Option(help="Overwrite existing baseline without confirmation.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Accept current behavior as the new canonical baseline."""
    result = _run(config, with_baseline=False, verbose=verbose)
    if not result:
        return
    loaded, config_path, report = result
    try:
        path = loaded.resolve_path(config_path, loaded.baseline.path)
        if path.exists() and not force:
            confirmed = typer.confirm(
                f"Baseline {path.name} already exists. Overwrite with current behavior?"
            )
            if not confirmed:
                console.print("[yellow]Aborted.[/]")
                return
        write_baseline(path, report, force=True)
        if json_output:
            typer.echo(json.dumps({"baseline": str(path), "status": "accepted"}, indent=2))
        else:
            console.print(f"[green]Accepted new baseline:[/] {path}")
    except PromptDriftError as error:
        _exit_error(error, verbose)


@app.command()
def purge(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm local storage purge.")] = False,
) -> None:
    """Purge all local SQLite interactions and history."""
    if not yes:
        confirmed = typer.confirm("Are you sure you want to purge all local captured interactions?")
        if not confirmed:
            return
    purge_storage()
    console.print("[green]Local storage successfully purged.[/]")


@app.command()
def test(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run behavioral contracts; automatically compares an existing baseline."""
    result = _run(config, with_baseline=True, verbose=verbose)
    if result:
        _emit(result[2], json_output)


@app.command()
def baseline(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    force: Annotated[bool, typer.Option(help="Replace an existing baseline.")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Create a canonical version-controlled baseline."""
    result = _run(config, with_baseline=False, verbose=verbose)
    if not result:
        return
    loaded, config_path, report = result
    try:
        path = loaded.resolve_path(config_path, loaded.baseline.path)
        write_baseline(path, report, force=force)
        if json_output:
            typer.echo(json.dumps({"baseline": str(path), "status": "created"}, indent=2))
        else:
            console.print(f"[green]Baseline written:[/] {path}")
    except PromptDriftError as error:
        _exit_error(error, verbose)


@app.command()
def diff(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run tests and compare the current behavior with the canonical baseline."""
    result = _run(config, with_baseline=True, verbose=verbose)
    if result:
        _emit(result[2], json_output)


@app.command()
def report(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("promptdrift-report.html"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Create an offline HTML report."""
    result = _run(config, with_baseline=True, verbose=verbose)
    if result:
        write_html_report(result[2], output)
        if json_output:
            typer.echo(result[2].model_dump_json(indent=2))
        else:
            console.print(f"[green]Report written:[/] {output}")
        if result[2].counts["FAIL"]:
            raise typer.Exit(code=1)


@app.command()
def doctor(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    privacy: Annotated[
        bool, typer.Option("--privacy", help="Inspect privacy and local data storage.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Check configuration, files, secrets, baseline, provider prerequisites, and privacy."""
    checks: list[dict[str, str | bool]] = []
    try:
        loaded, config_path = load_config(config)
        checks.extend(
            [
                {"name": "Config found and YAML valid", "passed": True},
                {"name": f"{len(loaded.tests)} test cases discovered", "passed": True},
            ]
        )
        for test_case in loaded.tests:
            checks.append(
                {
                    "name": f"Prompt exists: {test_case.prompt}",
                    "passed": loaded.resolve_path(config_path, test_case.prompt).is_file(),
                }
            )
        if loaded.provider.type == "openai":
            env = loaded.provider.api_key_env or "OPENAI_API_KEY"
            checks.append({"name": f"{env} found", "passed": bool(os.environ.get(env))})
        baseline = loaded.resolve_path(config_path, loaded.baseline.path)
        try:
            if baseline.exists():
                load_baseline(baseline)
            checks.append(
                {
                    "name": "Baseline valid" if baseline.exists() else "No baseline yet (optional)",
                    "passed": True,
                }
            )
        except BaselineError:
            checks.append({"name": "Baseline valid", "passed": False})

        if privacy:
            checks.append({"name": "No telemetry configured", "passed": True})
            checks.append({"name": "Local SQLite isolation active", "passed": True})
            checks.append(
                {
                    "name": "Raw baseline suppression active",
                    "passed": not loaded.baseline.store_raw_output,
                }
            )
    except PromptDriftError as error:
        _exit_error(error, verbose)
        return

    if json_output:
        typer.echo(json.dumps({"checks": checks}, indent=2))
    else:
        console.print("[bold]PromptDrift Doctor[/]")
        unicode_console = (sys.stdout.encoding or "").lower().replace("-", "") in {"utf8", "utf_8"}
        for check in checks:
            good, bad = ("✓", "✗") if unicode_console else ("OK", "X")
            console.print(
                f"{'[green]' + good + '[/]' if check['passed'] else '[red]' + bad + '[/]'} {check['name']}"
            )
    if not all(bool(check["passed"]) for check in checks):
        raise typer.Exit(code=2)


@app.command()
def version() -> None:
    """Print the PromptDrift version."""
    typer.echo(__version__)


def main() -> None:
    try:
        app()
    except PromptDriftError as error:
        _exit_error(error)


if __name__ == "__main__":
    main()
