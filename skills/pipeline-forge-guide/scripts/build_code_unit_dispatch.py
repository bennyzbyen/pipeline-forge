#!/usr/bin/env python3
"""Build a project-level dispatch view for confirmed PipelineForge code units."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("structured_facts.json must contain an object")
    return value


def command_for(unit: dict, facts: Path, output_root: Path) -> dict:
    unit_id = str(unit.get("code_unit_id", ""))
    route = str(unit.get("codegen_route", ""))
    unit_root = output_root / unit_id
    if route == "report-codegen":
        plan_dir = unit_root / "plan"
        project_dir = unit_root / "project"
        return {
            "plan": ["python", "<report-codegen>/scripts/build_report_codegen_plan.py", "--facts", str(facts), "--out", str(plan_dir), "--code-unit-id", unit_id],
            "generate": ["python", "<report-codegen>/scripts/scaffold_report_project.py", "--plan", str(plan_dir / "report_codegen_plan.json"), "--target", str(project_dir)],
            "verify": ["python", "<report-codegen>/scripts/verify_report_plan_semantics.py", "--project-dir", str(project_dir)],
        }
    if route == "data-sync-codegen":
        project_dir = unit_root / "project"
        return {
            "generate": ["python", "<data-sync-codegen>/scripts/scaffold_cot_sync_project.py", "--structured-facts", str(facts), "--output-dir", str(project_dir), "--code-unit-id", unit_id],
            "verify": ["python", "<data-sync-codegen>/scripts/verify_cot_manifest_semantics.py", "--project-dir", str(project_dir)],
        }
    return {"blocked": [f"No installed generator route for {route!r}."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    facts_path = args.facts.expanduser().resolve()
    facts = load(facts_path)
    plan = facts.get("code_unit_plan")
    units = facts.get("code_units")
    if not isinstance(plan, dict) or not isinstance(units, list):
        raise ValueError("two-level code-unit contract is required for project dispatch")
    if plan.get("status") != "confirmed":
        raise ValueError("project dispatch requires a confirmed code_unit_plan")
    rows = []
    for unit in units:
        readiness = unit.get("readiness") if isinstance(unit.get("readiness"), dict) else {}
        rows.append(
            {
                "code_unit_id": unit.get("code_unit_id", ""),
                "codegen_route": unit.get("codegen_route", ""),
                "component_kind": unit.get("component_kind", ""),
                "covered_waterlines": unit.get("covered_waterlines", []),
                "depends_on": unit.get("depends_on", []),
                "ready_for_codegen": readiness.get("ready_for_codegen") is True,
                "blockers": readiness.get("blockers", []),
                "commands": command_for(unit, facts_path, args.output_root.expanduser().resolve()),
            }
        )
    payload = {
        "status": "confirmed",
        "confirmed_count": plan.get("confirmed_count"),
        "dependency_graph": plan.get("dependency_graph", []),
        "ready_units": [item["code_unit_id"] for item in rows if item["ready_for_codegen"]],
        "blocked_units": [item["code_unit_id"] for item in rows if not item["ready_for_codegen"]],
        "code_units": rows,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
