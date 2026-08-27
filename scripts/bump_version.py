#!/usr/bin/env python3
"""Check or atomically bump all authoritative PipelineForge version sources."""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from release_versions import ROOT, VersionError, apply_bump, validate_version_consistency


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="New Semantic Version for a bump operation.")
    parser.add_argument("--check", action="store_true", help="Only verify current version consistency.")
    parser.add_argument("--expected-version", help="Expected version when used with --check.")
    parser.add_argument("--dry-run", action="store_true", help="Print the complete version diff without writing.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Release date in YYYY-MM-DD form.")
    parser.add_argument("--note", action="append", default=[], help="Release-note bullet; repeat for multiple bullets.")
    args = parser.parse_args()

    try:
        if args.check:
            if args.version or args.dry_run or args.note:
                parser.error("--check cannot be combined with version, --dry-run, or --note")
            version = validate_version_consistency(ROOT, expected_version=args.expected_version)
            print(f"PipelineForge authoritative versions are consistent: {version}")
            return 0

        if args.expected_version:
            parser.error("--expected-version requires --check")
        if not args.version:
            parser.error("version is required unless --check is used")
        changed = apply_bump(ROOT, args.version, args.date, args.note, dry_run=args.dry_run)
        verb = "Would update" if args.dry_run else "Updated"
        print(f"{verb} {len(changed)} authoritative version files to {args.version}")
        return 0
    except VersionError as exc:
        print(f"Version validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
