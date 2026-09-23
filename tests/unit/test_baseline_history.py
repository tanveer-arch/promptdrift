"""Tests for baseline history archiving and retrieval."""

from __future__ import annotations

import json

from promptdrift.engine.baseline_history import archive_baseline, list_baseline_history


class TestBaselineHistory:
    def test_archive_baseline(self, tmp_path):
        baseline_path = tmp_path / "baseline.json"
        history_dir = tmp_path / "history"

        # Creating a dummy baseline
        baseline_path.write_text(json.dumps({"test": "data"}))

        archive_path = archive_baseline(baseline_path, history_dir)

        assert archive_path is not None
        assert archive_path.is_file()
        assert "baseline_" in archive_path.name

        content = json.loads(archive_path.read_text())
        assert content["test"] == "data"

    def test_archive_missing_baseline(self, tmp_path):
        baseline_path = tmp_path / "nonexistent.json"
        history_dir = tmp_path / "history"

        assert archive_baseline(baseline_path, history_dir) is None

    def test_list_baseline_history(self, tmp_path):
        history_dir = tmp_path / "history"
        history_dir.mkdir()

        p1 = history_dir / "baseline_20240101_100000.json"
        p2 = history_dir / "baseline_20240102_100000.json"
        p3 = history_dir / "baseline_20240101_120000.json"

        p1.write_text("{}")
        p2.write_text("{}")
        p3.write_text("{}")

        paths = list_baseline_history(history_dir)

        # Newest first
        assert len(paths) == 3
        assert paths[0].name == "baseline_20240102_100000.json"
        assert paths[1].name == "baseline_20240101_120000.json"
        assert paths[2].name == "baseline_20240101_100000.json"

    def test_list_baseline_history_empty(self, tmp_path):
        history_dir = tmp_path / "history"
        assert list_baseline_history(history_dir) == []
