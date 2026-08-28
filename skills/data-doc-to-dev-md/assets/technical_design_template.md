---
document_type: technical-design
design_scope: hld-with-component-lld
project_type: data-sync / report / unknown
component_kind:
design_status: draft / review-ready / blocked
ready_for_codegen: false
structured_facts: structured_facts.json
questions: questions.md
---

# <project_name> Technical Design

## 1. Design Summary

- Source document:
- Original title:
- Document type: Technical Design
- Design coverage: HLD + component LLD
- Design status:
- Project type:
- Component kind:
- Ready for codegen:

## 2. HLD — High-Level Design

### 2.1 Data Architecture And Flow

1. DataSource:
2. DataProcess:
3. DataStorage:

### 2.2 Source Systems And Tables

| Source | Table / Path | Range | Fields | Notes |
|---|---|---|---|---|

### 2.3 Target Systems And Tables

| Storage | Database | Table | Grain | Write Mode | Notes |
|---|---|---|---|---|---|

### 2.4 Components And Responsibilities

| Component | Kind | Role | Status |
|---|---|---|---|

### 2.5 Scheduling And Rerun

- Schedule:
- Default period/date:
- Rerun parameter:
- Backfill behavior:

### 2.6 Write, Recovery And Idempotency Strategy

- Target:
- Delete old data:
- Insert method:
- HBase rowkey:
- FS evidence retention:
- Table-level exceptions:

### 2.7 Constraints And Risks

- Data volume / SLA:
- Performance constraints:
- Platform constraints:
- Known risks:

## 3. LLD — Component Implementation Contracts

### 3.1 Data Contract And Field Dictionary

| Target Field | Field Name | Type | Description | Source | Notes |
|---|---|---|---|---|---|

For COT/data-sync docs, include the sync matrix:

| Data Utilization | Source Table | Source Range | HBase Target | ClickHouse Target | Field Dictionary | Schedule |
|---|---|---|---|---|---|---|

For report docs, include source, target, and field-logic matrices:

| Storage | Table / Path | Range | Fields | Join / Filter |
|---|---|---|---|---|

| Target | Physical Table | Storage | Description | Field Dictionary |
|---|---|---|---|---|

### 3.2 Field Mapping And Processing Rules

| Target | Field | Source | Source Field | Transform / Rule | Confirmation |
|---|---|---|---|---|---|

### 3.3 KPI / Calculation Logic

| KPI / Field | Grain | Formula / Rule | Filters | Notes |
|---|---|---|---|---|

### 3.4 Parameter And Orchestration Contract

```json
{
  "running_env": "uat",
  "period": "",
  "current_date": "",
  "receiver_emails": []
}
```

### 3.5 Code Unit Plan

- Lifecycle: proposed / awaiting_user_confirmation / confirmed
- Proposed count:
- Confirmed count:
- Confidence:

| Code Unit | Route / Kind | Covered Waterlines | Parameter Profiles | Dependencies | Split / Merge Reason | Readiness |
|---|---|---|---|---|---|---|

Record the confirmation audit and per-unit blockers. Waterline count is evidence only; it does not directly determine code count.

## 4. Verification And Acceptance

- DataSource:
- DataProcess:
- DataStorage:
- HBase:
- ClickHouse:
- FS:
- Final metrics:

## 5. Codegen Readiness

- Contract version:
- Ready for codegen:
- Deployment validation: ready / review-required
- Machine-readable contract: `structured_facts.json#codegen_contract`
- Project contract: `structured_facts.json#project_contract`
- Code-unit plan: `structured_facts.json#code_unit_plan`
- Per-unit execution contracts: `structured_facts.json#code_units`

### Blocking Code Generation

-

### Open Questions

See `questions.md`.
