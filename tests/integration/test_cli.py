from typer.testing import CliRunner

from promptdrift.cli import app


def test_init_test_baseline_diff(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--directory", str(tmp_path)])
    assert result.exit_code == 0
    result = runner.invoke(app, ["test", "--config", str(tmp_path / "promptdrift.yaml"), "--json"])
    assert result.exit_code == 0
    assert '"status": "PASS"' in result.output
    result = runner.invoke(app, ["baseline", "--config", str(tmp_path / "promptdrift.yaml")])
    assert result.exit_code == 0
    result = runner.invoke(app, ["diff", "--config", str(tmp_path / "promptdrift.yaml")])
    assert result.exit_code == 0
