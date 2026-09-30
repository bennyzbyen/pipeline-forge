# Scoped revisions and delivery evidence

Use these helpers when an existing confirmed project changes or when stage reports
contradict each other. They use the standard library, do not require a private vault,
and never connect to deployment targets. Store their optional fields in existing
project artifacts; do not require additional deliverables for routine advice.

## Project checks versus plugin regression

`data-doc-to-dev-md/scripts/verify_schedule_boundary_planning.py --facts <facts>` is
a read-only project gate. It accepts low, medium and high confidence when the required
boundaries and confirmed mapping exist; confidence alone never establishes readiness.
Missing boundaries, unconfirmed mappings and invalid contracts return stable codes.
It does not rebuild a confirmed mapping or assume a fixed schedule/unit count.

`scripts/verify_feedback_workflows.py` and `verify_code_unit_contract_regression.py`
are synthetic plugin self-tests. Record their failures separately from project gates;
investigate which behavior is affected before declaring an unrelated project blocked.
Passing plugin fixtures is not a project's implementation or production verification.

## Revise an existing confirmed contract

Use `data-doc-to-dev-md/scripts/revise_confirmed_contract.py` for execution-contract
changes within existing code-unit and waterline boundaries. It cannot create a first
confirmation or merge/split/reassign units. Apply stricter repository rules; if a project
requires explicit first user confirmation, pass `--require-user-confirmation`.

Read the baseline facts first. Use the module's `fingerprint(facts)` (SHA256 of canonical
JSON, not raw file bytes) as `base_sha256`. The change document contains:

```json
{
  "base_sha256": "<canonical baseline SHA256>",
  "authorization": {
    "actor": "assistant",
    "evidence": "<actual user request or continuing authorization reference>",
    "reason": "<requested correction>"
  },
  "unit_changes": [{
    "code_unit_id": "<existing unit>",
    "execution_contract": {"<full replacement contract>": "<values>"},
    "waterline_contracts": {
      "<existing covered waterline>": {"<full replacement contract>": "<values>"}
    }
  }]
}
```

```text
python <data-doc-to-dev-md>/scripts/revise_confirmed_contract.py --facts <facts> --change <change.json> --out <revised-facts> --require-user-confirmation
```

The helper checks baseline freshness, updates only specified execution contracts and
their derived state/retry fields, refreshes fingerprints, preserves the original
confirmation audit, and appends a separate `revision_audit`. Other units are unchanged.
Every covered waterline must be supplied; their derived execution contract must agree
with the unit contract. Shared execution slices and specialized merge overrides need
an explicit project adapter or ordinary planning, not a guessed rewrite.

`revalidate_units` includes downstream dependants declared in the existing graph.
`validation_status=pending` is intentional: run the affected business/field/write
checks and entrypoint tests, update generated code and read-only contract snapshots,
then record their new evidence. The helper neither certifies these tests nor clears
pre-existing blockers. Updating a contract does not update business implementation.
Keep independent completed units and their results. Boundary or mapping changes use
the normal planning/audit workflow, respecting existing authorization.

## Derive stage status without rewriting history

Use `scripts/summarize_delivery_evidence.py --evidence <existing-report.json>` with an
`events` list. Each event requires `id`, `subject` (unit/check identifier), `stage`,
`status`, `source`, `evidence` (traceable reference), and timezone-aware `observed_at`.
Stages are `codegen`, `local_validation`, `deployment`, `business_acceptance`, and
`plugin_selftest`; statuses are `passed`, `failed`, `blocked`, and `unknown`.
Sources are `tool_report`, `log`, and `user_confirmation`.

Events remain immutable. A newer event may explicitly `supersedes: [<prior IDs>]`
only in the same stage and subject. Otherwise contradictory evidence stays a conflict.
Use separate subjects for independent checks; passing one check never erases another.
An absent stage is `not_recorded`, not passed. The tool summarizes supplied records;
it does not independently authenticate logs, confirmations or test execution.

User confirmation can support deployment/acceptance only. It cannot certify local
tests, codegen contracts or fault-injection checks. A self-test failure never changes
project readiness automatically. An accepted deployment does not erase a historical
generation-time deployment blocker or prove an unperformed recovery drill.

Optional `issues` have `id`, `stage`, `subject`, and `status` (`open`, `resolved`,
`superseded`). Closure requires `final_decision`, `recurrence_check`, and an
`evidence_id` referring to current, nonconflicting passed evidence in the same scope.
Superseded issues also require `superseded_by`; cycles and missing references fail.
The output lists active issues; retain the old records as history.

## Reuse existing capabilities for project-specific checks

Knowledge cards supply candidate rules and boundary cases. They do not patch a helper,
confirm private business facts, execute a project's tests or replace its latest evidence.
The following are scoped project checks, not new universal business defaults:

- **Environment parity:** separate connection/path/write switches from business filters
  and quality rules. Run the same frozen input through the actual entrypoints under
  each relevant profile using offline adapters. Compare keys, duplicates, row sets,
  values and filter counts, excluding only explicitly declared volatile metadata.
  Intentional business differences require their own requirement and difference test.
- **Published chain:** use existing lifecycle/delivery primitives and test the actual
  producer, manifest publication and consumer entrypoints in order. Consume published
  files, not an injected in-memory upstream result. Verify exact rows/schema/hash/batch,
  incomplete batches, duplicate keys, empty-output policy and upstream failure. Local
  adapter success does not prove remote storage or transaction success.
- **Business golden cases:** use the project's existing test suite and approved examples.
  Record source/rule version, organization/period, components, numerator, denominator,
  units, expected value, tolerance and authority. Cover the project's actual boundary
  cases and zero/missing denominators. Missing Excel formula caches or unapproved
  screenshot values are not authoritative expected results. Invalidate affected cases
  when the source rule is superseded; do not copy one project's named organizations.
- **Source/deployment preflight:** use explicit project profiles for sheets/headers,
  date coverage, source snapshot identity and confirmed row-count/quality thresholds.
  A single row is not universally invalid. Check declared target Python/API/dependency
  requirements and supplied DDL macros offline; unknown versions/macros remain unknown.
  Reuse DDL deployment profiles. Report read/calculate/write/publish stages and effective
  write switches separately; never enable production writes merely to pass a check.
- **Delivery identity:** in an existing delivery record list current source/contract
  revision, package hashes, validation evidence, replaced/withdrawn packages and the
  units to rerun. A shared logic change affects every consuming package. Link the
  authoritative business rule instead of duplicating it in multiple documents.

For existing directories use `implementation_contract.mode=preserve_existing` and the
project's native tests. The bundled report validator additionally accepts
`--implementation-status <external-md>` when only its status document lives outside
the code root. This flag does not make a bundled validator suitable for arbitrary
architectures and does not waive code, field or write checks.
