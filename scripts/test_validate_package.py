#!/usr/bin/env python3
"""Focused tests for PipelineForge package validation helpers."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import validate_package


class SourceSkillsCleanlinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temporary_directory.name)
        skill_root = self.repository_root / "skills" / "example-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text("example\n", encoding="utf-8")
        (self.repository_root / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
        (self.repository_root / ".gitignore").write_text(
            "skills/**/generated/\n",
            encoding="utf-8",
        )
        self.run_git("init", "--quiet")
        self.run_git("config", "user.name", "PipelineForge Validation")
        self.run_git("config", "user.email", "pipeline-forge@example.invalid")
        self.run_git("add", ".")
        self.run_git("commit", "--quiet", "-m", "Create validation fixture")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.repository_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_changes_outside_skills_are_allowed(self) -> None:
        (self.repository_root / "AGENTS.md").write_text("updated\n", encoding="utf-8")
        validate_package.validate_clean_source_skills(self.repository_root)

    def test_tracked_skill_changes_are_rejected(self) -> None:
        (self.repository_root / "skills" / "example-skill" / "SKILL.md").write_text(
            "changed\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(AssertionError, r"skills/ worktree must be clean"):
            validate_package.validate_clean_source_skills(self.repository_root)

    def test_ignored_skill_files_are_rejected(self) -> None:
        ignored_file = self.repository_root / "skills" / "example-skill" / "generated" / "template.sql"
        ignored_file.parent.mkdir()
        ignored_file.write_text("SELECT 1;\n", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, r"files not recorded by HEAD"):
            validate_package.validate_clean_source_skills(self.repository_root)


class ReleaseTagValidationTests(unittest.TestCase):
    def test_exact_v_prefixed_tag_is_accepted(self) -> None:
        validate_package.validate_release_tag("1.2.3", "v1.2.3")

    def test_mismatched_tag_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "release tag"):
            validate_package.validate_release_tag("1.2.3", "v1.2.4")


if __name__ == "__main__":
    unittest.main()
