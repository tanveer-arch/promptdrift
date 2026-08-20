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
from .engine.regression import compare_to_baseline
from .engine.runner import run_suite
from .errors import BaselineError, ConfigError, PromptDriftError, ProviderError, TemplateError
from .reports import print_report, write_html_report
from .storage import record_report

app = typer.Typer(add_completion=False, no_args_is_help=True, help="CI regression testing for LLM prompts.")
console = Console()


def _exit_error(error: Exception, verbose: bool = False) -> None:
    if verbose:
        raise error
    console.print(f"[red]Error:[/] {error}")
    code = 3 if isinstance(error, ProviderError) else 2 if isinstance(error, (ConfigError, BaselineError, TemplateError)) else 3
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
    directory: Annotated[Path, typer.Option("--directory", "-d", help="Project directory.")] = Path("."),
    force: Annotated[bool, typer.Option(help="Replace generated starter files.")] = False,
) -> None:
    """Create a usable offline starter project using the mock provider."""
    config_file = directory / "promptdrift.yaml"
    prompt_file = directory / "prompts" / "example.txt"
    if (config_file.exists() or prompt_file.exists()) and not force:
        console.print("[red]Error:[/] Starter files already exist. Use --force to replace them.")
        raise typer.Exit(code=2)
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("""version: 1\n\nprovider:\n  type: mock\n  model: local-echo\n\ndefaults:\n  temperature: 0\n  max_output_tokens: 500\n\nbaseline:\n  path: promptdrift.baseline.json\n\ntests:\n  - id: hello\n    prompt: prompts/example.txt\n    variables:\n      input: Hello\n    assertions:\n      - type: contains\n        value: Hello\n""", encoding="utf-8")
    prompt_file.write_text("Reply to this input exactly and concisely: {{ input }}\n", encoding="utf-8")
    console.print("[green]Created[/] promptdrift.yaml and prompts/example.txt\nRun: promptdrift test")


@app.command()
def test(
    config: Annotated[str, typer.Option("--config", "-c")] = "promptdrift.yaml",
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
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
    json_output: Annotated[bool, typer.Option("--json")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Check configuration, files, secrets, baseline, and provider prerequisites."""
    checks: list[dict[str, str | bool]] = []
    try:
        loaded, config_path = load_config(config)
        checks.extend([{"name": "Config found and YAML valid", "passed": True},
                       {"name": f"{len(loaded.tests)} test cases discovered", "passed": True}])
        for test_case in loaded.tests:
            checks.append({"name": f"Prompt exists: {test_case.prompt}", "passed": loaded.resolve_path(config_path, test_case.prompt).is_file()})
        if loaded.provider.type == "openai":
            env = loaded.provider.api_key_env or "OPENAI_API_KEY"
            checks.append({"name": f"{env} found", "passed": bool(os.environ.get(env))})
        baseline = loaded.resolve_path(config_path, loaded.baseline.path)
        try:
            if baseline.exists():
                load_baseline(baseline)
            checks.append({"name": "Baseline valid" if baseline.exists() else "No baseline yet (optional)", "passed": True})
        except BaselineError:
            checks.append({"name": "Baseline valid", "passed": False})
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
            console.print(f"{'[green]' + good + '[/]' if check['passed'] else '[red]' + bad + '[/]'} {check['name']}")
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
