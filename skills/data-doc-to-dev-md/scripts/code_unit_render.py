#!/usr/bin/env python3
"""Render the human-readable code-unit proposal and confirmation audit."""

from __future__ import annotations

from typing import Any, Mapping

from code_unit_contract import CONFIRMATION_QUESTION_ID


def render_code_unit_plan_markdown(facts: Mapping[str, Any]) -> str:
    plan = facts.get("code_unit_plan") if isinstance(facts.get("code_unit_plan"), Mapping) else {}
    units = facts.get("code_units") if isinstance(facts.get("code_units"), list) else []
    lines = [
        "## Code Unit Plan",
        "",
        f"- Status: `{plan.get('status', 'legacy')}`",
        f"- Proposed count: {plan.get('proposed_count', 'n/a')}",
        f"- Confirmed count: {plan.get('confirmed_count', 'not confirmed')}",
        f"- Confidence: {plan.get('confidence', 'n/a')}",
        "",
        "| Code unit | Route / kind | Covered waterlines | Parameterization | Readiness |",
        "| --- | --- | --- | --- | --- |",
    ]
    for unit in units:
        readiness = unit.get("readiness") if isinstance(unit.get("readiness"), Mapping) else {}
        parameterization = unit.get("parameterization") if isinstance(unit.get("parameterization"), Mapping) else {}
        route = unit.get("codegen_route", "")
        if not route:
            candidates = [
                str(item.get("route", ""))
                for item in unit.get("codegen_route_candidates", [])
                if isinstance(item, Mapping) and item.get("route")
            ]
            route = "unconfirmed; candidates=" + ", ".join(dict.fromkeys(candidates))
        lines.append(
            "| {id} | {route} / {kind} | {waterlines} | {parameterization} | {ready} |".format(
                id=unit.get("code_unit_id", ""),
                route=route,
                kind=unit.get("component_kind", ""),
                waterlines=", ".join(unit.get("covered_waterlines", [])),
                parameterization=parameterization.get("strategy", ""),
                ready=readiness.get("ready_for_codegen", False),
            )
        )
        lines.append("")
        lines.append(f"- `{unit.get('code_unit_id')}` reason: {unit.get('split_reason', '')}")
        if unit.get("depends_on"):
            lines.append(f"- `{unit.get('code_unit_id')}` depends on: {', '.join(unit.get('depends_on', []))}")
        if readiness.get("blockers"):
            lines.append(f"- `{unit.get('code_unit_id')}` blockers: {'; '.join(readiness.get('blockers', []))}")
    if plan.get("status") != "confirmed":
        lines.extend(["", f"- Blocking confirmation: `{CONFIRMATION_QUESTION_ID}`"])
    elif plan.get("confirmation_audit"):
        latest = plan["confirmation_audit"][-1]
        lines.extend(
            [
                "",
                "### Confirmation Audit",
                "",
                f"- Actor: {latest.get('actor', '')}",
                f"- Timestamp: {latest.get('timestamp', '')}",
                f"- Note: {latest.get('note', '') or 'No override note.'}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
