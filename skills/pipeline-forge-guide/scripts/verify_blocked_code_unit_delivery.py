#!/usr/bin/env python3
"""Verify blocked report/sync code units remain isolated, testable safe scaffolds."""

from __future__ import annotations

import compileall
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPT_DIR.parents[1]
DATA_DOC_SCRIPTS = SKILLS_ROOT / "data-doc-to-dev-md" / "scripts"
REPORT_SCRIPTS = SKILLS_ROOT / "report-codegen" / "scripts"
SYNC_SCRIPTS = SKILLS_ROOT / "data-sync-codegen" / "scripts"
sys.path.insert(0, str(DATA_DOC_SCRIPTS))

from code_unit_contract import apply_proposal, confirm_code_unit_plan  # noqa: E402


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def base_contract(project_type: str, component_kind: str) -> dict:
    return {
        "contract_version": 2,
        "project_type": project_type,
        "component_kind": component_kind,
        "components": [],
        "ready_for_codegen": True,
        "blockers": [],
        "open_questions": [],
        "validation_result": {
            "status": "passed",
            "deployment_status": "ready",
            "errors": [],
            "deployment_blockers": [],
            "warnings": [],
        },
    }


def report_facts() -> dict:
    result = {
        "report_targets": [{"target_name": "global_output", "description": "Global legacy output", "storage": "ClickHouse"}],
        "report_physical_targets": [{"table": "fixture.global_output", "description": "Global legacy output", "storage": "ClickHouse"}],
        "report_field_mappings": [
            {
                "inferred_target_name": "global_output",
                "inferred_physical_table": "fixture.global_output",
                "fields": [{"target_field": "id", "source_field": "id", "calculation_logic": "copy"}],
            }
        ],
        "codegen_contract": base_contract("report", "standard_report"),
        "waterlines": [
            {
                "waterline_id": "blocked_report",
                "codegen_route": "report-codegen",
                "component_kind": "standard_report",
                "logic_signature": "blocked_report_review",
                "state_compatibility_group": "report_state",
                "write_compatibility_group": "report_write",
                "deployment_group": "report_deployment",
                "failure_group": "report_failure",
                "boundary_confidence": "high",
                "execution_contract": {},
                "blockers": ["[sources] unit-scoped source evidence is missing"],
            }
        ],
    }
    apply_proposal(result)
    confirm_code_unit_plan(
        result,
        {
            "units": [
                {
                    "code_unit_id": "blocked_report_unit",
                    "covered_waterlines": ["blocked_report"],
                    "codegen_route": "report-codegen",
                    "component_kind": "standard_report",
                }
            ]
        },
        timestamp="2026-08-28T00:00:00+00:00",
    )
    return result


def sync_facts() -> dict:
    result = {
        "cot_report_tables": [
            {
                "business_desc": "Blocked sync review fixture",
                "report_type": "without period",
                "source_range": "full",
                "clickhouse_table": "fixture.sync_table",
                "source_hbase_table": "fixture.sync_table",
            }
        ],
        "codegen_contract": base_contract("data-sync", "cot_table_sync"),
        "waterlines": [
            {
                "waterline_id": "blocked_sync",
                "codegen_route": "data-sync-codegen",
                "component_kind": "cot_table_sync",
                "logic_signature": "blocked_sync_review",
                "state_compatibility_group": "sync_state",
                "write_compatibility_group": "sync_write",
                "deployment_group": "sync_deployment",
                "failure_group": "sync_failure",
                "boundary_confidence": "high",
                "covered_tables": ["fixture.sync_table"],
                "execution_contract": {"tables": [{"table": "fixture.sync_table"}]},
                "blockers": ["[writes] sync target transaction is missing"],
            }
        ],
    }
    apply_proposal(result)
    confirm_code_unit_plan(
        result,
        {
            "units": [
                {
                    "code_unit_id": "blocked_sync_unit",
                    "covered_waterlines": ["blocked_sync"],
                    "codegen_route": "data-sync-codegen",
                    "component_kind": "cot_table_sync",
                }
            ]
        },
        timestamp="2026-08-28T00:00:01+00:00",
    )
    return result


def verify_safe_project(project: Path, unit_id: str) -> dict:
    assert compileall.compile_dir(project, quiet=1), unit_id
    test_result = run([sys.executable, "-m", "pytest", "-q", str(project / "tests")], SKILLS_ROOT.parent)
    assert "1 passed" in test_result.stdout, test_result.stdout
    snapshot = json.loads((project / "CODE_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
    marker = json.loads((project / "SAFE_SCAFFOLD.json").read_text(encoding="utf-8"))
    assert snapshot["code_unit_id"] == unit_id, snapshot
    assert snapshot["contract"]["readiness"]["ready_for_codegen"] is False, snapshot
    assert marker["runtime_enabled"] is False, marker
    return {"code_unit_id": unit_id, "compiled": True, "tests": "passed", "runtime_enabled": False}


def main() -> int:
    with TemporaryDirectory(prefix="pipelineforge-blocked-code-units-") as temp:
        root = Path(temp)
        report_path = root / "report_facts.json"
        report_path.write_text(json.dumps(report_facts(), ensure_ascii=False, indent=2), encoding="utf-8")
        report_plan_dir = root / "report_plan"
        run(
            [
                sys.executable,
                str(REPORT_SCRIPTS / "build_report_codegen_plan.py"),
                "--facts",
                str(report_path),
                "--out",
                str(report_plan_dir),
                "--code-unit-id",
                "blocked_report_unit",
            ],
            SKILLS_ROOT.parent,
        )
        report_plan = json.loads((report_plan_dir / "report_codegen_plan.json").read_text(encoding="utf-8"))
        assert report_plan["outputs"] == [], report_plan["outputs"]
        report_project = root / "blocked_report_project"
        run(
            [
                sys.executable,
                str(REPORT_SCRIPTS / "scaffold_report_project.py"),
                "--plan",
                str(report_plan_dir / "report_codegen_plan.json"),
                "--target",
                str(report_project),
                "--allow-blocked-scaffold",
            ],
            SKILLS_ROOT.parent,
        )

        sync_path = root / "sync_facts.json"
        sync_path.write_text(json.dumps(sync_facts(), ensure_ascii=False, indent=2), encoding="utf-8")
        sync_project = root / "blocked_sync_project"
        run(
            [
                sys.executable,
                str(SYNC_SCRIPTS / "scaffold_cot_sync_project.py"),
                "--structured-facts",
                str(sync_path),
                "--output-dir",
                str(sync_project),
                "--code-unit-id",
                "blocked_sync_unit",
                "--allow-blocked-scaffold",
            ],
            SKILLS_ROOT.parent,
        )

        results = [
            verify_safe_project(report_project, "blocked_report_unit"),
            verify_safe_project(sync_project, "blocked_sync_unit"),
        ]
        print(
            json.dumps(
                {
                    "status": "passed",
                    "safe_scaffold_count": 2,
                    "report_global_output_fallback": False,
                    "projects": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
