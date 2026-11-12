"""Selective checks use the same prompt paths as the runner."""

import json
import os
import subprocess

import pytest
import yaml
from typer.testing import CliRunner

from promptdrift.cli import app


@pytest.fixture
def git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=.disabled-hooks",
                *args,
            ],
            cwd=root,
            text=True,
        ).strip()

    git("init", "-q")
    return root, git


def _create_suite(config_path, prompts):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tests = []
    for test_id, prompt in prompts.items():
        path = config_path.parent / prompt
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("good", encoding="utf-8")
        tests.append(
            {
                "id": test_id,
                "prompt": prompt,
                "assertions": [{"type": "exact_match", "value": "good"}],
            }
        )
    config_path.write_text(
        yaml.safe_dump({"version": 1, "provider": {"type": "mock"}, "tests": tests}),
        encoding="utf-8",
    )
    result = _invoke("baseline", config_path)
    assert result.exit_code == 0, result.output


def _invoke(command, config_path, *args):
    return CliRunner().invoke(app, [command, "--config", str(config_path), "--json", *args])


def _commit(git):
    git("add", ".")
    git("commit", "-qm", "fixture")
    return git("rev-parse", "HEAD")


def test_nested_config_collision_detects_regression(git_repo):
    root, git = git_repo
    config_path = root / "suite" / "promptdrift.yaml"
    _create_suite(config_path, {"changed": "prompt.txt", "unrelated": "suite/prompt.txt"})
    base = _commit(git)
    (root / "suite" / "prompt.txt").write_text("bad", encoding="utf-8")
    _commit(git)
    assert git("diff", "--name-only", f"{base}...HEAD") == "suite/prompt.txt"

    control = _invoke("test", config_path)
    assert control.exit_code == 1, control.output
    assert {run["test_id"]: run["status"] for run in json.loads(control.output)["tests"]} == {
        "changed": "FAIL",
        "unrelated": "PASS",
    }

    result = _invoke("check", config_path, "--base", base)
    data = json.loads(result.output)
    assert [run["test_id"] for run in data["report"]["tests"]] == ["changed"]
    assert result.exit_code == 1, result.output
    evaluation = data["report"]["tests"][0]["evaluations"][0]
    assert evaluation == {
        "passed": False,
        "assertion": "exact_match",
        "expected": "good",
        "actual": "bad",
        "reason": "Output does not exactly match expected value.",
        "severity": "fail",
    }
    assert {
        case["scenario_id"]: case["classification"] for case in data["impact"]["scenarios"]
    } == {
        "changed": "REGRESSED",
        "unrelated": "NOT_EVALUATED",
    }


@pytest.mark.parametrize(
    ("config_dir", "prompts", "changed_files", "evaluated"),
    [
        (".", {"a": "a.txt", "b": "b.txt"}, ["a.txt"], {"a"}),
        (
            "suite",
            {"a": "./prompt.txt", "shared": "../suite/prompt.txt", "b": "other.txt"},
            ["suite/prompt.txt"],
            {"a", "shared"},
        ),
        (
            "suite",
            {"a": "../a.txt", "b": "b.txt", "c": "c.txt"},
            ["a.txt", "suite/b.txt"],
            {"a", "b"},
        ),
        (
            "suite",
            {"a": "a.txt", "b": "b.txt"},
            ["suite/a.txt", "source.py"],
            {"a", "b"},
        ),
        ("suite", {"a": "a.txt", "b": "b.txt"}, [], {"a", "b"}),
        (
            "suite",
            {"a": " café.txt", "b": "other.txt"},
            ["suite/ café.txt"],
            {"a"},
        ),
        pytest.param(
            "suite",
            {"a": "sub\\prompt.txt", "b": "other.txt"},
            ["suite/sub/prompt.txt"],
            {"a"},
            marks=pytest.mark.skipif(os.name != "nt", reason="Backslash is a separator on Windows"),
        ),
    ],
    ids=["root", "shared-normalized", "multiple", "unmapped", "no-changes", "quoted", "windows"],
)
def test_selective_check_path_cases(git_repo, config_dir, prompts, changed_files, evaluated):
    root, git = git_repo
    config_path = root / config_dir / "promptdrift.yaml"
    _create_suite(config_path, prompts)
    base = _commit(git)
    for name in changed_files:
        (root / name).write_text("bad", encoding="utf-8")
    if changed_files:
        _commit(git)
    # The changed-file contract must hold even when the user's Git config asks
    # for paths relative to the directory where Git was invoked.
    git("config", "diff.relative", "true")

    result = _invoke("check", config_path, "--base", base)
    data = json.loads(result.output)
    runs = {run["test_id"]: run for run in data["report"]["tests"]}
    assert set(runs) == evaluated
    failing = {
        test_id
        for test_id, prompt in prompts.items()
        if (config_path.parent / prompt).read_text(encoding="utf-8") == "bad"
    }
    assert result.exit_code == (1 if failing else 0), result.output
    assert {test_id for test_id, run in runs.items() if run["status"] == "FAIL"} == failing
    classifications = {
        case["scenario_id"]: case["classification"] for case in data["impact"]["scenarios"]
    }
    expected = dict.fromkeys(prompts, "NOT_EVALUATED")
    expected.update(dict.fromkeys(evaluated, "UNCHANGED"))
    expected.update(dict.fromkeys(failing, "REGRESSED"))
    assert classifications == expected


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged", "staged"])
def test_nested_check_without_base(git_repo, staged):
    root, git = git_repo
    config_path = root / "suite" / "promptdrift.yaml"
    _create_suite(config_path, {"changed": "prompt.txt", "unrelated": "suite/prompt.txt"})
    _commit(git)
    (root / "suite" / "prompt.txt").write_text("bad", encoding="utf-8")
    if staged:
        git("add", "suite/prompt.txt")
    git("config", "diff.relative", "true")

    result = _invoke("check", config_path)
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert [run["test_id"] for run in data["report"]["tests"]] == ["changed"]
    assert data["impact"]["regressed"] == 1
    assert data["impact"]["not_evaluated"] == 1


def test_unknown_git_root_runs_full_suite(git_repo, monkeypatch):
    root, git = git_repo
    config_path = root / "suite" / "promptdrift.yaml"
    _create_suite(config_path, {"a": "a.txt", "b": "b.txt"})
    base = _commit(git)
    (root / "suite" / "a.txt").write_text("bad", encoding="utf-8")
    _commit(git)
    monkeypatch.setattr("promptdrift.git.GitContext.get_repo_root", lambda self: None)

    result = _invoke("check", config_path, "--base", base)
    assert result.exit_code == 1, result.output
    assert {run["test_id"] for run in json.loads(result.output)["report"]["tests"]} == {"a", "b"}


def test_absolute_prompt_path_is_selected(git_repo):
    root, git = git_repo
    config_path = root / "suite" / "promptdrift.yaml"
    prompt = root / "prompt.txt"
    _create_suite(config_path, {"a": str(prompt), "b": "other.txt"})
    base = _commit(git)
    prompt.write_text("bad", encoding="utf-8")
    _commit(git)

    result = _invoke("check", config_path, "--base", base)
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert [run["test_id"] for run in data["report"]["tests"]] == ["a"]
    assert data["impact"]["not_evaluated"] == 1
