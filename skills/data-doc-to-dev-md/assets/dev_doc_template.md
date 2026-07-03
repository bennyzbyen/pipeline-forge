# <project_name> Development Document

## 1. Project Overview

- Source document:
- Project type: data-sync / report
- Business goal:
- Primary reference code:
- Structured facts file:
- Component hints:

## 2. Source Tables

| Source | Table / Path | Range | Fields | Notes |
|---|---|---|---|---|

## 3. Target Tables

| Storage | Database | Table | Grain | Write Mode | Notes |
|---|---|---|---|---|---|

## 4. Field Dictionary

| Target Field | Field Name | Type | Description | Source | Notes |
|---|---|---|---|---|---|

## 5. Field Mapping

| Target Field | Source Table | Source Field | Transform / Rule | Confirmation |
|---|---|---|---|---|

For COT/data-sync docs, include a sync matrix:

| Data Utilization | Source Table | Source Range | HBase Target | ClickHouse Target | Field Dictionary | Schedule |
|---|---|---|---|---|---|---|

For report docs, include source, target, and field-logic matrices:

| Storage | Table / Path | Range | Fields | Join / Filter |
|---|---|---|---|---|

| Target | Physical Table | Storage | Description | Field Dictionary |
|---|---|---|---|---|

| Target | Field | Source | Source Field | Rule | EO Rule | DMS Rule |
|---|---|---|---|---|---|---|

## 6. Data Processing Flow

1. DataSource:
2. DataProcess:
3. DataStorage:

## 7. KPI / Calculation Logic

| KPI / Field | Grain | Formula / Rule | Filters | Notes |
|---|---|---|---|---|

## 8. Write Strategy

- Target:
- Delete old data:
- Insert method:
- HBase rowkey:
- FS evidence retention:
- Table-level exceptions:

## 9. Scheduling And Rerun

- Schedule:
- Default period/date:
- Rerun parameter:
- Backfill behavior:

## 10. Parameter Design

```json
{
  "running_env": "uat",
  "period": "",
  "current_date": "",
  "receiver_emails": []
}
```

## 11. Log Verification Plan

- DataSource:
- DataProcess:
- DataStorage:
- HBase:
- ClickHouse:
- FS:
- Diagnostic manifest / plan:
- Final metrics:

## 12. Open Questions

- 
