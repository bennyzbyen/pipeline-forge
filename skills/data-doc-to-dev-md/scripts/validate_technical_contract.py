#!/usr/bin/env python3
"""Validate a structured_facts.json codegen contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from technical_contract import validate_contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True, help="structured_facts.json path")
    parser.add_argument("--json-out", type=Path, help="Optional validation JSON output")
    parser.add_argument("--strict-deployment", action="store_true", help="Fail when deployment blockers remain")
    args = parser.parse_args()
    payload = json.loads(args.facts.read_text(encoding="utf-8"))
    contract = payload.get("codegen_contract") if isinstance(payload, dict) else None
    if not isinstance(contract, dict):
        raise ValueError("structured facts must contain an object at codegen_contract")
    result = validate_contract(contract)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if result["status"] != "passed":
        return 1
    if args.strict_deployment and result["deployment_status"] != "ready":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
