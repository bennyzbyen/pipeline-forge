#!/usr/bin/env python3
"""Regression-test deterministic low-confidence handling of weak log evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ANALYZER = Path(__file__).resolve().parent / "analyze_data_job_log.py"


def run_cli(log_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ANALYZER), "--log", str(log_path), "--format", "json", "--output", str(output_path)],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def run_twice(log_path: Path, root: Path, stem: str) -> dict[str, object]:
    payloads: list[dict[str, object]] = []
    for index in range(2):
        output = root / f"{stem}_{index}.json"
        completed = run_cli(log_path, output)
        combined = completed.stdout + completed.stderr
        assert completed.returncode == 0, combined
        assert "Traceback (most recent call last)" not in combined, combined
        payloads.append(json.loads(output.read_text(encoding="utf-8")))
    assert payloads[0] == payloads[1], f"{stem}: CLI output was not deterministic"
    return payloads[0]


def run_regression() -> dict[str, object]:
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="data_job_log_input_robustness_") as temp_dir:
        root = Path(temp_dir)

        empty = root / "empty.log"
        empty.write_text("  \n\t", encoding="utf-8")
        empty_output = root / "empty.json"
        completed = run_cli(empty, empty_output)
        combined = completed.stdout + completed.stderr
        assert completed.returncode != 0, combined
        assert "log is empty" in combined.lower(), combined
        assert "Traceback (most recent call last)" not in combined, combined
        assert not empty_output.exists(), "empty log left a misleading diagnosis artifact"
        results.append({"case": "empty_log", "status": "passed", "exit_code": completed.returncode})

        truncated = root / "truncated.log"
        truncated.write_text(
            "2026-08-27 INFO running env=qa params loaded\n"
            "2026-08-27 ERROR hbase insert failed table=fixture_target\n"
            "2026-08-27 ERROR worker output truncated after 4096 bytes\n",
            encoding="utf-8",
        )
        payload = run_twice(truncated, root, "truncated")
        assert payload["primary_pattern_id"] == "hbase_operation_failure", payload
        assert payload["confidence"] == "low", payload
        assert payload["diagnosis_status"] == "hypothesis", payload
        assert "截断" in str(payload["confidence_reason"]), payload
        results.append({"case": "truncated_log", "status": "passed", "confidence": payload["confidence"]})

        competing = root / "competing.log"
        competing.write_text(
            "2026-08-27 INFO running env=qa params loaded\n"
            "Traceback (most recent call last):\n"
            "  File \"plugin_main.py\", line 20, in run\n"
            "ValueError: source parameter is required\n"
            "Traceback (most recent call last):\n"
            "  File \"plugin_main.py\", line 4, in <module>\n"
            "SyntaxError: invalid syntax\n",
            encoding="utf-8",
        )
        payload = run_twice(competing, root, "competing")
        assert payload["primary_pattern_id"] == "missing_runtime_param", payload
        assert payload["competing_pattern_ids"] == ["dependency_or_import"], payload
        assert payload["confidence"] == "low", payload
        assert payload["diagnosis_status"] == "hypothesis", payload
        results.append(
            {
                "case": "competing_errors",
                "status": "passed",
                "primary_pattern_id": payload["primary_pattern_id"],
                "confidence": payload["confidence"],
            }
        )

    return {
        "status": "passed",
        "case_count": len(results),
        "cases": results,
        "external_service_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
