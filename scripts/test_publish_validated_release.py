#!/usr/bin/env python3
"""Offline tests for retry-safe GitHub Release publication."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import publish_validated_release


class FakeGitHub:
    def __init__(self, release: dict | None = None, assets: dict[str, bytes] | None = None) -> None:
        self.release = release
        self.assets = dict(assets or {})
        self.commands: list[list[str]] = []

    def __call__(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(arguments)
        operation = arguments[:2]
        if operation == ["release", "view"]:
            if self.release is None:
                return subprocess.CompletedProcess(arguments, 1, "", "release not found")
            payload = dict(self.release)
            payload["assets"] = [{"name": name} for name in sorted(self.assets)]
            return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")
        if operation == ["release", "create"]:
            if self.release is not None:
                return subprocess.CompletedProcess(arguments, 1, "", "release already exists")
            self.release = {"isDraft": True}
            return subprocess.CompletedProcess(arguments, 0, "created", "")
        if operation == ["release", "upload"]:
            self.assets[Path(arguments[3]).name] = Path(arguments[3]).read_bytes()
            self.assets[Path(arguments[4]).name] = Path(arguments[4]).read_bytes()
            return subprocess.CompletedProcess(arguments, 0, "uploaded", "")
        if operation == ["release", "download"]:
            download_root = Path(arguments[arguments.index("--dir") + 1])
            for name, content in self.assets.items():
                (download_root / name).write_bytes(content)
            return subprocess.CompletedProcess(arguments, 0, "downloaded", "")
        if operation == ["release", "edit"]:
            assert self.release is not None
            self.release["isDraft"] = False
            return subprocess.CompletedProcess(arguments, 0, "published", "")
        raise AssertionError(f"unexpected fake gh command: {arguments}")


class ReleasePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.archive = self.root / publish_validated_release.ARCHIVE_NAME
        self.checksum = self.root / publish_validated_release.CHECKSUM_NAME
        self.archive.write_bytes(b"validated release archive")
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.checksum.write_text(
            f"{digest}  {publish_validated_release.ARCHIVE_NAME}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def publish(self, fake: FakeGitHub) -> str:
        return publish_validated_release.publish_release(
            repository="example/pipeline-forge",
            tag="v1.2.3",
            title="PipelineForge v1.2.3",
            asset_root=self.root,
            archive=self.archive,
            checksum=self.checksum,
            runner=fake,
        )

    def test_new_release_is_uploaded_verified_and_published(self) -> None:
        fake = FakeGitHub()
        self.assertEqual(self.publish(fake), "published")
        self.assertFalse(fake.release["isDraft"])
        self.assertEqual(
            set(fake.assets),
            {
                publish_validated_release.ARCHIVE_NAME,
                publish_validated_release.CHECKSUM_NAME,
            },
        )

    def test_matching_published_release_is_idempotent(self) -> None:
        fake = FakeGitHub(
            release={"isDraft": False},
            assets={
                self.archive.name: self.archive.read_bytes(),
                self.checksum.name: self.checksum.read_bytes(),
            },
        )
        self.assertEqual(self.publish(fake), "already-published")
        self.assertFalse(any(command[:2] == ["release", "upload"] for command in fake.commands))

    def test_retry_replaces_only_expected_assets_in_existing_draft(self) -> None:
        fake = FakeGitHub(
            release={"isDraft": True},
            assets={
                self.archive.name: b"partial upload from an earlier attempt",
                self.checksum.name: b"partial checksum",
            },
        )
        self.assertEqual(self.publish(fake), "published")
        self.assertEqual(fake.assets[self.archive.name], self.archive.read_bytes())
        self.assertEqual(fake.assets[self.checksum.name], self.checksum.read_bytes())

    def test_published_release_with_different_asset_is_rejected(self) -> None:
        fake = FakeGitHub(
            release={"isDraft": False},
            assets={self.archive.name: b"different"},
        )
        with self.assertRaisesRegex(
            publish_validated_release.ReleasePublishError,
            "unexpected asset set",
        ):
            self.publish(fake)
        self.assertFalse(any(command[:2] == ["release", "upload"] for command in fake.commands))

    def test_published_release_with_same_names_but_different_bytes_is_rejected(self) -> None:
        fake = FakeGitHub(
            release={"isDraft": False},
            assets={
                self.archive.name: b"different",
                self.checksum.name: self.checksum.read_bytes(),
            },
        )
        with self.assertRaisesRegex(
            publish_validated_release.ReleasePublishError,
            "differs from this run's validated build",
        ):
            self.publish(fake)

    def test_draft_with_unexpected_asset_is_rejected(self) -> None:
        fake = FakeGitHub(
            release={"isDraft": True},
            assets={"unreviewed.exe": b"unexpected"},
        )
        with self.assertRaisesRegex(
            publish_validated_release.ReleasePublishError,
            "unexpected assets",
        ):
            self.publish(fake)
        self.assertFalse(any(command[:2] == ["release", "upload"] for command in fake.commands))

    def test_local_checksum_mismatch_is_rejected_before_gh(self) -> None:
        self.archive.write_bytes(b"mutated after validation")
        fake = FakeGitHub()
        with self.assertRaisesRegex(
            publish_validated_release.ReleasePublishError,
            "checksum mismatch",
        ):
            self.publish(fake)
        self.assertEqual(fake.commands, [])

    def test_assets_outside_validated_root_are_rejected(self) -> None:
        other_root = self.root / "other"
        other_root.mkdir()
        external_archive = other_root / self.archive.name
        shutil.copy2(self.archive, external_archive)
        with self.assertRaisesRegex(
            publish_validated_release.ReleasePublishError,
            "direct file in the validated asset root",
        ):
            publish_validated_release.validate_local_assets(
                self.root,
                external_archive,
                self.checksum,
            )


if __name__ == "__main__":
    unittest.main()
