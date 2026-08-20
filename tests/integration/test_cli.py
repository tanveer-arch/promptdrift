"""Integration tests for the PromptDrift CLI."""
import json

from typer.testing import CliRunner

from promptdrift.cli import app

runner = CliRunner()


class TestInitCommand:
    def test_creates_starter_files(self, tmp_path):
        result = runner.invoke(app, ["init", "--directory", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "promptdrift.yaml").is_file()
        assert (tmp_path / "prompts" / "example.txt").is_file()

    def test_refuses_overwrite_without_force(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["init", "--directory", str(tmp_path)])
        assert result.exit_code == 2

    def test_force_replaces_files(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["init", "--directory", str(tmp_path), "--force"])
        assert result.exit_code == 0


class TestTestCommand:
    def test_runs_and_passes(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["test", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["test", "--config", str(tmp_path / "promptdrift.yaml"), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["tests"][0]["status"] == "PASS"

    def test_missing_config_fails(self, tmp_path):
        result = runner.invoke(app, ["test", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


class TestBaselineCommand:
    def test_creates_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0
        assert (tmp_path / "promptdrift.baseline.json").is_file()

    def test_refuses_overwrite_without_force(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code != 0

    def test_force_replaces_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml"), "--force"])
        assert result.exit_code == 0

    def test_json_output(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml"), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "baseline" in data


class TestDiffCommand:
    def test_diff_with_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
        result = runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_diff_without_baseline(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0  # No baseline = no comparison, just assertions


class TestReportCommand:
    def test_creates_html_report(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        output_path = tmp_path / "report.html"
        result = runner.invoke(app, [
            "report", "--config", str(tmp_path / "promptdrift.yaml"),
            "--output", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.is_file()


class TestDoctorCommand:
    def test_doctor_passes(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["doctor", "--config", str(tmp_path / "promptdrift.yaml")])
        assert result.exit_code == 0

    def test_doctor_json(self, tmp_path):
        runner.invoke(app, ["init", "--directory", str(tmp_path)])
        result = runner.invoke(app, ["doctor", "--config", str(tmp_path / "promptdrift.yaml"), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "checks" in data
        assert all(c["passed"] for c in data["checks"])

    def test_doctor_missing_config(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code != 0


class TestVersionCommand:
    def test_prints_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestFullWorkflow:
    def test_init_test_baseline_diff(self, tmp_path):
        """Full lifecycle: init → test → baseline → diff."""
        assert runner.invoke(app, ["init", "--directory", str(tmp_path)]).exit_code == 0
        assert runner.invoke(app, ["test", "--config", str(tmp_path / "promptdrift.yaml"), "--json"]).exit_code == 0
        assert runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")]).exit_code == 0
        assert runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")]).exit_code == 0
