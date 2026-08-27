#!/usr/bin/env python3
"""Regression tests for PipelineForge version and release-tag gates."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import release_versions


ROOT = Path(__file__).resolve().parents[1]


class VersionFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        for relative_path in release_versions.AUTHORITY_PATHS:
            source = ROOT / relative_path
            destination = self.root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self.current = release_versions.validate_version_consistency(self.root)
        major, minor, patch, _ = release_versions.parse_semver(self.current)
        self.next_version = f"{major}.{minor}.{patch + 1}"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_dry_run_prints_diff_without_writing(self) -> None:
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        output = io.StringIO()
        release_versions.apply_bump(
            self.root,
            self.next_version,
            "2099-01-02",
            ["Exercise the deterministic release fixture."],
            dry_run=True,
            output=output,
        )
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertIn(f"## {self.next_version} - 2099-01-02", output.getvalue())

    def test_bump_updates_every_authoritative_location(self) -> None:
        release_versions.apply_bump(
            self.root,
            self.next_version,
            "2099-01-02",
            ["Exercise the deterministic release fixture."],
        )
        self.assertEqual(release_versions.validate_version_consistency(self.root), self.next_version)
        manifest = json.loads((self.root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], self.next_version)
        marketplace = json.loads(
            (self.root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["plugins"][0]["source"]["ref"], f"v{self.next_version}")
        self.assertIn(
            f"--ref v{self.next_version}",
            (self.root / "INSTALL.md").read_text(encoding="utf-8"),
        )

    def test_drift_is_rejected(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(self.current, "9.9.9", 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(release_versions.VersionError, "authoritative versions"):
            release_versions.validate_version_consistency(self.root)

    def test_release_tag_must_exactly_match_version(self) -> None:
        release_versions.validate_release_tag(self.current, f"v{self.current}")
        release_versions.validate_release_tag(self.current, f"refs/tags/v{self.current}")
        with self.assertRaisesRegex(release_versions.VersionError, "release tag"):
            release_versions.validate_release_tag(self.current, self.current)
        with self.assertRaisesRegex(release_versions.VersionError, "release tag"):
            release_versions.validate_release_tag(self.current, "v9.9.9")


if __name__ == "__main__":
    unittest.main()
