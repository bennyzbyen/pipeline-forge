#!/usr/bin/env python3
# GPT-6 適配變更說明：確認輸出改為如實記錄 mapping adoption 的 actor/note，不把已授權的 assistant 決策冒充用戶再次確認；保留契約驗證。
"""Propose, confirm, rebuild, or validate a two-level code-unit contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from code_unit_contract import (
    CONFIRMATION_BLOCKER,
    CONFIRMATION_QUESTION_ID,
    apply_proposal,
    confirm_code_unit_plan,
    validate_code_unit_contract,
)
from code_unit_render import render_code_unit_plan_markdown


DESIGN_START = "<!-- PIPELINEFORGE_CODE_UNIT_PLAN_START -->"
DESIGN_END = "<!-- PIPELINEFORGE_CODE_UNIT_PLAN_END -->"
QUESTIONS_START = "<!-- PIPELINEFORGE_CODE_UNIT_AUDIT_START -->"
QUESTIONS_END = "<!-- PIPELINEFORGE_CODE_UNIT_AUDIT_END -->"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def replace_marked_section(path: Path, start: str, end: str, content: str) -> None:
    if not path.exists():
        return
    original = path.read_text(encoding="utf-8")
    section = f"{start}\n{content.rstrip()}\n{end}"
    if start in original and end in original:
        before = original.split(start, 1)[0].rstrip()
        after = original.split(end, 1)[1].lstrip()
        updated = f"{before}\n\n{section}\n"
        if after:
            updated += f"\n{after}"
    else:
        updated = original.rstrip() + f"\n\n{section}\n"
    path.write_text(updated, encoding="utf-8")


def resolve_confirmation_line(path: Path, replacement: str) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = [replacement if CONFIRMATION_QUESTION_ID in line else line for line in lines]
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def render_questions_audit(facts: dict) -> str:
    plan = facts.get("code_unit_plan", {})
    units = facts.get("code_units", [])
    lines = ["## Code Unit Confirmation"]
    if plan.get("status") != "confirmed":
        lines.extend(["", f"- {CONFIRMATION_BLOCKER}"])
        return "\n".join(lines) + "\n"
    audit = plan.get("confirmation_audit") or []
    resolution = (
        "resolved by explicit user confirmation"
        if audit and audit[-1].get("actor") == "user"
        else "resolved by audited mapping adoption"
    )
    lines.extend(
        [
            "",
            f"- `{CONFIRMATION_QUESTION_ID}`: {resolution}; see actor and note below.",
            f"- Confirmed count: {plan.get('confirmed_count')}",
        ]
    )
    if plan.get("confirmation_audit"):
        latest = plan["confirmation_audit"][-1]
        lines.append(
            f"- Audit: {latest.get('timestamp', '')}; actor={latest.get('actor', '')}; "
            f"note={latest.get('note', '') or 'none'}"
        )
    lines.extend(["", "### Per-Unit Blocking Code Generation", ""])
    blocked = False
    for unit in units:
        blockers = unit.get("readiness", {}).get("blockers", [])
        if not blockers:
            continue
        blocked = True
        lines.append(f"- `{unit.get('code_unit_id')}`: {'; '.join(str(item) for item in blockers)}")
    if not blocked:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--facts", type=Path, required=True, help="Input structured_facts.json.")
    result.add_argument("--out", type=Path, required=True, help="Output structured_facts.json.")
    result.add_argument("--technical-design", type=Path, help="Optional technical_design.md to update in place.")
    result.add_argument("--questions", type=Path, help="Optional questions.md to update in place.")
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("propose", help="Rebuild a proposal and invalidate any earlier confirmation.")
    confirm = subparsers.add_parser("confirm", help="Apply an authorized, evidence-reviewed mapping and record its actual actor.")
    confirm.add_argument("--mapping", type=Path, required=True, help="JSON with a units array.")
    confirm.add_argument("--actor", default="user", help="Audit actor label.")
    confirm.add_argument("--note", default="", help="Audit note describing a merge/split override.")
    subparsers.add_parser("validate", help="Validate without changing the contract.")
    return result


def main() -> int:
    args = parser().parse_args()
    facts = load_json(args.facts)
    if args.command == "propose":
        apply_proposal(facts)
    elif args.command == "confirm":
        confirm_code_unit_plan(facts, load_json(args.mapping), actor=args.actor, note=args.note)
    validation = validate_code_unit_contract(facts)
    if args.command == "validate":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 0 if validation["status"] in {"passed", "legacy_compatible"} else 1
    if validation["status"] != "passed":
        raise ValueError("code-unit contract validation failed: " + "; ".join(validation["errors"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.technical_design:
        if facts.get("code_unit_plan", {}).get("status") == "confirmed":
            resolve_confirmation_line(
                args.technical_design,
                "- Code-unit mapping confirmed; see the Code Unit Plan confirmation audit below.",
            )
        replace_marked_section(
            args.technical_design,
            DESIGN_START,
            DESIGN_END,
            render_code_unit_plan_markdown(facts),
        )
    if args.questions:
        if facts.get("code_unit_plan", {}).get("status") == "confirmed":
            resolve_confirmation_line(
                args.questions,
                f"- [{CONFIRMATION_QUESTION_ID}] Resolved by audited mapping adoption; see actor and note in the audit below.",
            )
        replace_marked_section(
            args.questions,
            QUESTIONS_START,
            QUESTIONS_END,
            render_questions_audit(facts),
        )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
