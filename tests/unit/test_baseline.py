from pathlib import Path

import pytest

from promptdrift.engine.baseline import load_baseline, write_baseline
from promptdrift.errors import BaselineError
from promptdrift.models import RegressionReport, TestRun


def report():
    return RegressionReport(provider="mock", model="m", tests=[TestRun(test_id="x", provider="mock", model="m", input="p", output="o", latency_ms=1)])


def test_baseline_roundtrip_and_no_silent_overwrite(tmp_path: Path):
    path = tmp_path / "baseline.json"
    write_baseline(path, report())
    assert load_baseline(path).tests["x"].status == "PASS"
    with pytest.raises(BaselineError):
        write_baseline(path, report())
