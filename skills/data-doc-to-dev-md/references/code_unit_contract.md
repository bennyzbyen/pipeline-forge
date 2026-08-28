# Two-Level Code-Unit Contract

Use this contract when a project may contain more than one independently generated or deployed code unit. The formal handoff remains `technical_design.md`, `structured_facts.json`, and `questions.md`.

## Lifecycle

- `proposed`: an internal proposal exists but has not yet been presented as the blocking review state.
- `awaiting_user_confirmation`: the proposal is visible and full code generation is forbidden.
- `confirmed`: the user confirmed or overrode the mapping and the mapping passed boundary validation.

Changing waterline boundary evidence changes `boundary_evidence_fingerprint`. A previously confirmed plan then becomes invalid and must be rebuilt and confirmed again.

## Project-Level Contract

`structured_facts.json.project_contract` owns:

- project metadata and evidence summary;
- shared field, source, and parameter contracts;
- confirmed code-unit count and mapping;
- dependency graph;
- user merge/split overrides and audit timestamps;
- overall readiness without hiding per-unit blockers.

`structured_facts.json.code_unit_plan` owns the proposal and confirmation lifecycle:

```json
{
  "plan_version": 1,
  "status": "awaiting_user_confirmation",
  "proposed_count": 2,
  "confirmed_count": null,
  "covered_waterlines": ["daily", "period"],
  "parameterization": [],
  "split_reason": "...",
  "confidence": "medium",
  "proposed_mapping": [],
  "confirmed_mapping": [],
  "dependency_graph": [],
  "boundary_evidence_fingerprint": "sha256...",
  "confirmation_audit": []
}
```

Waterline count is inventory evidence only. Automatic grouping compares algorithm identity, safe parameterization, state/watermark compatibility, write-transaction compatibility, deployment and rerun boundaries, failure isolation, routes, and dependencies.

Schedule-derived waterlines are enriched from task identity, Data Utilization ownership, temporal grain, target descriptions, field mappings, business rules, source evidence, and write contracts. Every inferred dimension keeps its evidence status. An unresolved route is stored as `codegen_route_candidates[]` plus a routing blocker; it is never silently inherited from the project-level type. Missing algorithm, state, write, deployment, failure, or dependency evidence appears in the proposed unit's blockers before confirmation.

## Per-Code-Unit Contract

Every entry in `structured_facts.json.code_units[]` is independently selectable and validates:

- `code_unit_id`, lifecycle status, `codegen_route`, and `component_kind`;
- auditable route candidates when the route is unresolved;
- `covered_waterlines` and `waterline_bindings`;
- parameter profiles and the parameterization strategy;
- split/merge reason, confidence, and dependencies;
- one bounded `execution_contract` with sources, steps, outputs, writes, state/watermark, retry, rerun, empty-output behavior, and failure behavior;
- unit-specific tests, readiness, and blockers.

One waterline may appear in multiple units only when each binding declares a distinct `execution_slice`. Multiple waterlines may share one unit when their hard state, write, deployment, failure, and route boundaries are compatible. A user override may merge different algorithms into a branching implementation, but cannot override incompatible state, write transaction, deployment, failure-isolation, or codegen-route boundaries.

Generated code directories receive `CODE_UNIT_CONTRACT.json`. It is a read-only snapshot for audit and tests, not a new source of truth.

## Confirmation CLI

Rebuild or invalidate a proposal:

```powershell
python .\scripts\manage_code_unit_plan.py --facts <structured_facts.json> --out <structured_facts.json> --technical-design <technical_design.md> --questions <questions.md> propose
```

Confirm a user-approved mapping:

```powershell
python .\scripts\manage_code_unit_plan.py --facts <structured_facts.json> --out <structured_facts.json> --technical-design <technical_design.md> --questions <questions.md> confirm --mapping <confirmed_mapping.json> --actor user --note "Merge three proposed units into two"
```

The mapping JSON contains a `units` array. Each unit declares `code_unit_id`, `covered_waterlines`, route, component kind, and optional execution slice, dependencies, execution contract, parameterization, tests, and audit reason.

## Compatibility

- Inputs without `project_contract`, `code_unit_plan`, and `code_units` remain legacy-compatible and continue through the old single-component path.
- New two-level inputs never fall back silently. Awaiting or stale confirmation is rejected.
- A confirmed one-unit project may omit `--code-unit-id`; a confirmed multi-unit project must select it explicitly.
- The three-file handoff remains unchanged. The two-level structure is embedded in `structured_facts.json`, rendered in `technical_design.md`, and audited in `questions.md`.
