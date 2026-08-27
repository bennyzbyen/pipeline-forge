#!/usr/bin/env python3
"""Negative regression tests for ZIP pre-extraction safety checks."""

from __future__ import annotations

import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

import validate_archive_safety


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_archive(
        self,
        members: list[tuple[str, bytes, int | None]],
        name: str = "fixture.zip",
    ) -> Path:
        archive_path = self.root / name
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive_path, "w") as archive:
                for member_name, content, external_attr in members:
                    info = zipfile.ZipInfo(member_name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    if external_attr is not None:
                        info.create_system = 3
                        info.external_attr = external_attr
                    archive.writestr(info, content)
        return archive_path

    def assert_rejected(self, members: list[tuple[str, bytes, int | None]], pattern: str) -> None:
        archive_path = self.make_archive(members)
        with self.assertRaisesRegex(validate_archive_safety.ArchiveSafetyError, pattern):
            validate_archive_safety.validate_archive(archive_path)

    def test_safe_archive_is_accepted(self) -> None:
        archive_path = self.make_archive(
            [("pipeline-forge/README.md", b"safe\n", (stat.S_IFREG | 0o644) << 16)]
        )
        self.assertEqual(
            validate_archive_safety.validate_archive(archive_path),
            ["pipeline-forge/README.md"],
        )

    def test_absolute_path_is_rejected(self) -> None:
        self.assert_rejected([("/pipeline-forge/evil.txt", b"x", None)], "absolute path")

    def test_parent_traversal_is_rejected(self) -> None:
        self.assert_rejected([("pipeline-forge/../evil.txt", b"x", None)], "unsafe path segment")

    def test_backslash_parent_traversal_is_rejected(self) -> None:
        self.assert_rejected(
            [(r"pipeline-forge\..\evil.txt", b"x", None)],
            "unsafe path segment",
        )

    def test_member_outside_allowed_root_is_rejected(self) -> None:
        self.assert_rejected([("other-root/evil.txt", b"x", None)], "outside the allowed")

    def test_duplicate_member_is_rejected(self) -> None:
        self.assert_rejected(
            [
                ("pipeline-forge/same.txt", b"one", None),
                ("pipeline-forge/same.txt", b"two", None),
            ],
            "duplicate",
        )

    def test_case_collision_is_rejected(self) -> None:
        self.assert_rejected(
            [
                ("pipeline-forge/Readme.md", b"one", None),
                ("pipeline-forge/README.md", b"two", None),
            ],
            "case or type collision",
        )

    def test_symlink_member_is_rejected(self) -> None:
        self.assert_rejected(
            [("pipeline-forge/link", b"outside", (stat.S_IFLNK | 0o777) << 16)],
            "symbolic-link",
        )

    def test_reparse_member_is_rejected(self) -> None:
        self.assert_rejected(
            [
                (
                    "pipeline-forge/reparse",
                    b"outside",
                    validate_archive_safety.REPARSE_POINT_ATTRIBUTE,
                )
            ],
            "reparse-point",
        )

    def test_file_ancestor_conflict_is_rejected(self) -> None:
        self.assert_rejected(
            [
                ("pipeline-forge/parent", b"file", None),
                ("pipeline-forge/parent/child.txt", b"child", None),
            ],
            "nested below a file",
        )

    def test_windows_ambiguous_name_is_rejected(self) -> None:
        self.assert_rejected(
            [("pipeline-forge/name./child.txt", b"x", None)],
            "Windows-ambiguous",
        )


if __name__ == "__main__":
    unittest.main()
