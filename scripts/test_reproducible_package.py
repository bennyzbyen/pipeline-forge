#!/usr/bin/env python3
"""Regression tests for deterministic PipelineForge download archives."""

from __future__ import annotations

import hashlib
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_reproducible_zip


ROOT = Path(__file__).resolve().parents[1]


class ReproduciblePackageTests(unittest.TestCase):
    def test_two_builds_are_byte_identical_with_stable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            first = build_reproducible_zip.build_archive(ROOT, temporary_root / "first.zip")
            second = build_reproducible_zip.build_archive(ROOT, temporary_root / "second.zip")

            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
            self.assertEqual(hashlib.sha256(first_bytes).digest(), hashlib.sha256(second_bytes).digest())
            self.assertEqual(first_bytes, second_bytes)

            with zipfile.ZipFile(first) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                self.assertEqual(names, sorted(names))
                self.assertTrue(names)
                self.assertTrue(all(name.startswith("pipeline-forge/") for name in names))
                self.assertTrue(all(info.date_time == build_reproducible_zip.FIXED_TIMESTAMP for info in infos))
                self.assertTrue(all(info.create_system == 3 for info in infos))
                self.assertTrue(
                    all(stat.S_IMODE(info.external_attr >> 16) == 0o644 for info in infos)
                )
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))


if __name__ == "__main__":
    unittest.main()
