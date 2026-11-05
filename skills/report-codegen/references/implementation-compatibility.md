# Preserve implementation compatibility

A business contract states observable behavior: inputs, source/target schema, formulas,
ordering, write scope, failures and result protocol. It does not require a DSL interpreter,
a specific class name, a shared package, or a new directory tree.

When the user supplies an existing project or established project pattern, inspect its
actual entrypoint and called code first. Preserve that structure by default. Choose
`preserve_existing`; use `native_python` for a new implementation that follows a selected
Python pattern without the bundled interpreter. Use `bundled` only when that layout fits
the task or a framework migration was requested. Do not request another approval when
existing instructions already select the approach; record the evidence and proceed.

Carry the choice in the existing facts/plan, rather than adding a mandatory deliverable:

```json
{
  "implementation_contract": {
    "mode": "preserve_existing",
    "reference_supplied": true,
    "evidence": ["user-selected source project and entrypoint"],
    "entrypoint": "plugin_main.py",
    "entry_symbol": "main",
    "result_location": "declared by entry protocol",
    "deployment_unit": "self-contained directory"
  }
}
```

Preserve this per code unit when units have different structures. In particular compare:

- accepted parameter envelope, unwrap count, working-directory behavior and result path;
- function/class signatures and the actual import/call path, not just available filenames;
- standalone deployment contents, shared package imports and platform wrappers;
- return value/JSON serialization and error propagation;
- existing deterministic tests and execution commands.

### Refactoring a deployed operator or deriving a new year

Trace one real run from the previous entrypoint through parameter resolution, source
selection, both writers and watermark handling. Carry over the provider of each value.
Pipeline parameters can own the physical targets, update column, period or batch,
replacement key and ordered RowKey columns. Retain their existing defaults, identifier
checks and write scope. An example Excel row or field dictionary is evidence for that
run. Turning its values into an equality check rejects other valid runs.

For a whole-row sync, retain ordered runtime column discovery (`SELECT *` with cursor
metadata, or `SHOW COLUMNS` and a dynamic select list). Carry that order through CSV,
ClickHouse and HBase, including new nullable business columns. Check the keys consumed
by the operation. Keep explicit projections for reports that define them. Add a target
schema/type preflight only when the source or current requirement calls for one.
Test a new column and a different valid parameter on the native execution path.

For Gateway, trace the client back to the selected operator's configuration. Preserve
the file, credential provider, environment selector and per-unit/profile routing.
An environment selector such as `running_env` can choose QA/UAT/PROD while the key pair
comes from a file. Changing the provider, moving a key to an environment variable or
rotating credentials requires a specific instruction. A private operator ZIP must carry
the authorized runtime config and the original fixed `gateway/`, `hbase/` and `fs/`
files. Keep shared core and unit-specific config separate when assembling split ZIPs.

Use the project's packager. Compare the **finished ZIP** to the authoritative unit
directory and fixed-package source, with the entrypoint at its deployment path.

```text
python <pipeline-forge-guide>/scripts/verify_operator_package.py --zip <operator.zip> --unit-root <unit> --config cot_config/plugin_config.py --platform-root <original-operator>
```

Select the actual config path, repeat `--config` for other runtime config files and
use `--entrypoint` for a different layout. For split operators run this once per ZIP
with its own trusted unit root. Exercise the packaged entrypoint offline with fake
clients to check each profile routes to that unit's provider. Report paths and pass/fail
only. Keep secret values out of logs, handoffs, examples and the plugin. For a shareable
sanitized example use the separate candidate workflow.

Use an approved, populated config as the reference for a credential-bearing delivery.
Matching placeholder files still need deployment configuration. Gateway application
activation is a separate platform check.

Missing correctness facts remain blockers only for the dependent code. Do not invent a
deployment model or treat every optional implementation detail as a confirmation gate.

`scaffold_report_project.py` emits the bundled layout. It rejects explicit
preserve_existing/native_python plans before changing the output directory. For those
modes, adapt the scoped source files directly, or use the existing
`scaffold_reference_report_project.py` workflow for a sanitized candidate. Keep the user's
source unchanged unless edits there are requested. Do not call the bundled scaffolder
and then describe its new tree as structure-preserving.

Native code still needs exact field/formula/output checks and fake-adapter failure tests.
Use its own test suite plus `verify_generated_safety.py`; generic scaffold validators
that require ReportPipeline/DataSource classes do not establish compatibility for a
different architecture. Never add those classes merely to make such a validator pass.

## FMOS as a generated example

The user identifies FMOS as developed with PipelineForge and reports difficulty with
entrypoint/framework differences. Treat it as generated-project feedback, not independent
production evidence supporting PipelineForge's architecture.

The inspected Labor entrypoints call `fmos_labor.shared.runtime.main(unit_id, params)`;
a neighboring main_execute.py can still contain ReportPipeline without being called by
that entrypoint. Static imports do not establish all deployed paths. The shared runtime
also uses project-specific Python runners; its contract interpreter is not proof that
the whole project is successfully expressed by the generic DSL.

The inspected `project_tables` adapter builds a DataFrame with the declared output columns
before invoking the interpreter. Absent row keys may therefore already be converted to
nulls. A passing column-presence check at that point proves neither original-key presence
nor non-null business completeness. Validate required record keys before shaping, and
validate nullability/defaults using the project's explicit schema. Do not assume that all
nulls are errors or add a universal non-null rule.

Use FMOS-inspired synthetic cases to check unknown operators, missing fields and output
column order in the existing interpreter. Do not infer from those passing tests that
FMOS was easy to develop, that its packaging is portable, or that the user should adopt
the same framework. No new interpreter is introduced for this case.

QAS is also user-identified generated code from an older PipelineForge version (exact
version unspecified). Keep its rule tests and observed failures, but do not count it as
an independent hand-written architecture precedent. Original requirements remain separate
evidence; their authorship is not inferred from the code origin.
