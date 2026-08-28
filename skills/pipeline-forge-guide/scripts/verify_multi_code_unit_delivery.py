#!/usr/bin/env python3
"""Generate and verify multiple confirmed report code units independently."""

from __future__ import annotations

import compileall
import copy
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
sys.path.insert(0, str(DATA_DOC_SCRIPTS))
sys.path.insert(0, str(REPORT_SCRIPTS))

from code_unit_contract import apply_proposal, confirm_code_unit_plan  # noqa: E402
from verify_generic_report_runtime_semantics import build_plan as build_fixture_plan  # noqa: E402


def execution_contract(output_name: str) -> dict:
    contract = copy.deepcopy(build_fixture_plan("standard_report")["execution_contract"])
    original = next(iter(contract["outputs"]))
    contract["outputs"][output_name] = contract["outputs"].pop(original)
    write = contract["writes"].pop(original)
    write["table"] = f"fixture.{output_name}"
    contract["writes"][output_name] = write
    return contract


def structured_facts() -> dict:
    columns = ["region", "period", "revenue", "store_count", "avg_revenue"]
    rules = [
        {"target_field": item, "source_field": item, "calculation_logic": "confirmed fixture execution contract"}
        for item in columns
    ]
    result = {
        "report_sources": [
            {"storage": "injected", "table_or_path": "orders", "fields": ["store_code", "period", "amount", "quantity", "status"]},
            {"storage": "injected", "table_or_path": "stores", "fields": ["store_code", "region"]},
        ],
        "report_targets": [
            {"target_name": "daily_output", "description": "Daily output", "storage": "ClickHouse"},
            {"target_name": "period_output", "description": "Period output", "storage": "ClickHouse"},
        ],
        "report_physical_targets": [
            {"table": "fixture.daily_output", "description": "Daily output", "storage": "ClickHouse"},
            {"table": "fixture.period_output", "description": "Period output", "storage": "ClickHouse"},
        ],
        "report_field_mappings": [
            {
                "inferred_target_name": "daily_output",
                "inferred_target_description": "Daily output",
                "inferred_physical_table": "fixture.daily_output",
                "fields": copy.deepcopy(rules),
            },
            {
                "inferred_target_name": "period_output",
                "inferred_target_description": "Period output",
                "inferred_physical_table": "fixture.period_output",
                "fields": copy.deepcopy(rules),
            },
        ],
        "codegen_contract": {
            "contract_version": 2,
            "project_type": "report",
            "component_kind": "standard_report",
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
        },
        "waterlines": [
            {
                "waterline_id": "daily",
                "codegen_route": "report-codegen",
                "component_kind": "standard_report",
                "logic_signature": "daily_algorithm",
                "state_compatibility_group": "daily_state",
                "write_compatibility_group": "daily_write",
                "boundary_confidence": "high",
                "execution_contract": execution_contract("daily_output"),
                "covered_tables": ["daily_output"],
                "tests": [{"name": "daily_contract_runtime"}],
            },
            {
                "waterline_id": "period",
                "codegen_route": "report-codegen",
                "component_kind": "standard_report",
                "logic_signature": "period_algorithm",
                "state_compatibility_group": "period_state",
                "write_compatibility_group": "period_write",
                "boundary_confidence": "high",
                "execution_contract": execution_contract("period_output"),
                "covered_tables": ["period_output"],
                "tests": [{"name": "period_contract_runtime"}],
            },
        ],
    }
    apply_proposal(result)
    return result


def run(command: list[str], cwd: Path, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if expect_success and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    if not expect_success and completed.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {' '.join(command)}")
    return completed


def main() -> int:
    with TemporaryDirectory(prefix="pipelineforge-multi-code-unit-") as temp:
        root = Path(temp)
        facts = structured_facts()
        awaiting_path = root / "awaiting.json"
        awaiting_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

        # The report plan builder is a codegen gateway and must reject an unconfirmed project.
        rejected = run(
            [sys.executable, str(REPORT_SCRIPTS / "build_report_codegen_plan.py"), "--facts", str(awaiting_path), "--out", str(root / "rejected")],
            SKILLS_ROOT.parent,
            expect_success=False,
        )
        assert "confirmation" in (rejected.stdout + rejected.stderr).lower(), rejected.stderr

        confirm_code_unit_plan(
            facts,
            {
                "units": [
                    {"code_unit_id": "daily_unit", "covered_waterlines": ["daily"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
                    {"code_unit_id": "period_unit", "covered_waterlines": ["period"], "codegen_route": "report-codegen", "component_kind": "standard_report"},
                ]
            },
            timestamp="2026-08-28T00:00:00+00:00",
        )
        facts_path = root / "structured_facts.json"
        facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

        results = []
        for unit_id, output_name in (("daily_unit", "daily_output"), ("period_unit", "period_output")):
            plan_dir = root / f"plan_{unit_id}"
            project_dir = root / f"project_{unit_id}"
            run(
                [
                    sys.executable,
                    str(REPORT_SCRIPTS / "build_report_codegen_plan.py"),
                    "--facts",
                    str(facts_path),
                    "--out",
                    str(plan_dir),
                    "--code-unit-id",
                    unit_id,
                ],
                SKILLS_ROOT.parent,
            )
            plan_path = plan_dir / "report_codegen_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            assert plan["summary"]["ready_for_codegen"] is True, plan["summary"]
            assert plan["summary"]["code_unit_id"] == unit_id, plan["summary"]
            assert [item["target_name"] for item in plan["outputs"]] == [output_name], plan["outputs"]
            run(
                [sys.executable, str(REPORT_SCRIPTS / "scaffold_report_project.py"), "--plan", str(plan_path), "--target", str(project_dir)],
                SKILLS_ROOT.parent,
            )
            assert compileall.compile_dir(project_dir, quiet=1), unit_id
            test_result = run([sys.executable, "-m", "pytest", "-q", str(project_dir / "tests")], SKILLS_ROOT.parent)
            assert "1 passed" in test_result.stdout, test_result.stdout
            verify_path = root / f"verify_{unit_id}.json"
            run(
                [sys.executable, str(REPORT_SCRIPTS / "verify_report_plan_semantics.py"), "--project-dir", str(project_dir), "--json-out", str(verify_path)],
                SKILLS_ROOT.parent,
            )
            verification = json.loads(verify_path.read_text(encoding="utf-8"))
            snapshot = json.loads((project_dir / "CODE_UNIT_CONTRACT.json").read_text(encoding="utf-8"))
            assert snapshot["code_unit_id"] == unit_id, snapshot
            assert verification["status"] == "passed", verification
            assert verification["implementation_ready"] is True, verification
            results.append(
                {
                    "code_unit_id": unit_id,
                    "output": output_name,
                    "compiled": True,
                    "tests": "passed",
                    "readiness": verification["implementation_ready"],
                }
            )

        assert results[0]["output"] != results[1]["output"], results
        print(json.dumps({"status": "passed", "unit_count": 2, "units": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
