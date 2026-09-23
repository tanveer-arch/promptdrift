"""Tests for git revision and prompt hash computation."""

from __future__ import annotations

from unittest.mock import patch

from promptdrift.git import GitContext


class TestGitRevision:
    def test_compute_prompt_hash(self, tmp_path):
        ctx = GitContext(root=tmp_path)

        p1 = tmp_path / "prompts" / "a.txt"
        p2 = tmp_path / "prompts" / "b.txt"
        p1.parent.mkdir()
        p1.write_text("hello", encoding="utf-8")
        p2.write_text("world", encoding="utf-8")

        # Hash of [p1, p2]
        hash1 = ctx.compute_prompt_hash([p1, p2])
        assert hash1 is not None

        # Order shouldn't matter
        hash2 = ctx.compute_prompt_hash([p2, p1])
        assert hash1 == hash2

        # Modifying a file changes hash
        p1.write_text("changed", encoding="utf-8")
        hash3 = ctx.compute_prompt_hash([p1, p2])
        assert hash3 != hash1

    def test_compute_prompt_hash_empty_or_missing(self, tmp_path):
        ctx = GitContext(root=tmp_path)

        assert ctx.compute_prompt_hash([]) is None

        missing = tmp_path / "missing.txt"
        assert ctx.compute_prompt_hash([missing]) is None

    @patch("promptdrift.git.GitContext.get_changed_files")
    def test_has_uncommitted_prompt_changes(self, mock_changed, tmp_path):
        ctx = GitContext(root=tmp_path)

        p1 = tmp_path / "prompts" / "a.txt"
        p1.parent.mkdir()
        p1.write_text("hi")

        # No changed files
        mock_changed.return_value = []
        assert not ctx.has_uncommitted_prompt_changes([p1])

        # Changed file matches
        mock_changed.return_value = ["prompts/a.txt"]
        assert ctx.has_uncommitted_prompt_changes([p1])

        # Changed file doesn't match
        mock_changed.return_value = ["other.txt"]
        assert not ctx.has_uncommitted_prompt_changes([p1])
