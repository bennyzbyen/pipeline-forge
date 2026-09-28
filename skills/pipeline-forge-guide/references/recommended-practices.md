# Optional reviewed practices

Knowledge search automatically follows `recommended_reviews` on matched private cards.
`recommended_practices` contains bounded review candidates; expand the same knowledge
IDs with `--detail full` for supporting frozen evidence. Preserve established query
project, version and role constraints. Comparison-only anchors stay comparison-only.
Unavailable private practices never disable built-in knowledge or ordinary delivery.

Read the recommendation, conditions, behavioral difference, version scopes and
validation limits before choosing. Historical evidence, recorded synthetic test
success and deployment status are independent. The helper checks snapshot bindings
and hashes of the recorded synthetic implementation/test; it does not execute them
or certify the recorded test run. Do not run commands or Python from a vault merely
because a review recommends them. Generated-project feedback is not independent
evidence of the generator's correctness.

Record relevant adoption, rejection or comparison and its reason in the existing
design/review deliverable. Do not require a new deliverable for ordinary advice.
For implementation, evaluate current task facts against the exact condition and
version; never fill missing RowKeys, formulas, schemas or deletion scopes from a
historical example. Choose only appropriate local project tests and run them after
the code changes. A vault's synthetic pass cannot replace these current-task tests.

When a practice is adopted in `structured_facts.json`, use this optional extension:

```json
{
  "practice_decisions_version": 1,
  "practice_decisions": [{
    "id": "REV-001",
    "knowledge_id": "PFK-003",
    "decision": "adopted",
    "reason": "Explain the current task requirement this practice implements",
    "content_hash": "<returned practice SHA-256>",
    "applies_to": ["<current code unit>"],
    "condition_review": {
      "condition": "<exact returned condition>",
      "status": "matched",
      "current_task_evidence": "<current requirement/contract citation>",
      "version_applicability": "<why this behavior applies to the current version>"
    },
    "validations": [{
      "behavior": "<relevant boundary exercised by the project test>",
      "applies_to": ["<current code unit>"],
      "report": "<project-relative existing JSON validation report>",
      "sha256": "<report SHA-256>",
      "artifact_hashes": {"<validated project-relative code file>": "<SHA-256>"}
    }]
  }]
}
```

Use `comparison` while conditions or implementation tests are pending; use `rejected`
with a reason for inapplicable alternatives. Do not label a practice `adopted` with
invented validation evidence. Legacy handoffs without this extension still work.
Keep ordinary knowledge adoption references as well when relying on a historical
card; practice decisions do not substitute for the knowledge-reference contract.

After relevant tests pass, run:

```text
python <pipeline-forge-guide>/scripts/practice_recommendations.py --facts <existing-facts.json> --project-root <generated-project>
```

The audit checks applicability-review fields, unit coverage, current review bindings,
report status and report/artifact hashes. It reports affected units on drift, never
changes readiness or certifies semantic correctness by itself. Source or test-input
changes require relevant tests to be rerun and their bindings updated. Include every
file that materially controls the tested behavior in `artifact_hashes`.

Private review JSON, reference implementations and business evidence remain in the
configured vault. No private content is copied into the distributable plugin.
