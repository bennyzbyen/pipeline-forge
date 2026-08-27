# DOCX Extraction Rules

## Evidence Priority

1. Embedded Excel workbooks in `word/embeddings/*.xlsx`
2. Word tables in `word/document.xml`
3. Word paragraph text and heading-like styles
4. Screenshots or images, only when no structured table is available

## Extraction Expectations

- Keep original field names, table names, Chinese labels, and formulas.
- Export embedded Excel sheets and Word tables to CSV with UTF-8 BOM so Excel on Windows can open Chinese text.
- Do not infer table grain, rowkey, delete conditions, or schedule unless explicitly present.
- Any missing business rule belongs in `questions.md`.
- In multi-document projects, keep source-document provenance on extracted facts so PRD and waterline evidence can be audited separately.
- When PRD and waterline facts overlap, prefer waterline/DataEngine facts for physical tables, field dictionaries, target storage, and schedules; use PRD facts for business goals, KPI descriptions, abnormal rules, UI aggregation, and feedback behavior. Record material conflicts in `questions.md`.

## Common DataEngine Document Signals

- Source sections: `Source 数据源`, `数据源详情`, `链接信息`, `数据列表`, `Data Source`
- Target sections: `Data Target`, `目标表`, `Data Storage`, `目标表字典`
- Processing sections: `Data Transformation Logic`, `数据流程`, `同步逻辑`, `写入流程`
- Schedule sections: `Pipeline Planning`, `运行时间`, `调度`, `频率`, `重跑`
- Report sections: `报表字段逻辑`, `KPI`, `汇总逻辑`, `字段映射`

## Output Quality Bar

- Keep the formal codegen handoff to `technical_design.md`, `structured_facts.json`, and `questions.md`; `extracted/` is supporting evidence only.
- `technical_design.md` should be readable without opening the original DOCX.
- `technical_design.md` should separate HLD-level flow/components from LLD-level field, processing, parameter, and write contracts without creating extra design files.
- If embedded Excel contains a report/sync matrix, `technical_design.md` must include the actual rows, not only the CSV filenames.
- Generate and review `dev_doc/structured_facts.json` whenever recognizable matrices exist.
- `structured_facts.json.codegen_contract` should expose routing, components, readiness, and blockers for downstream codegen.
- `questions.md` should classify every ambiguity as codegen-blocking, deployment confirmation, or non-blocking and render the same stable `TC-CG-*`, `TC-DP-*`, or `TC-NB-*` ID stored in `structured_facts.json.codegen_contract.open_questions`.
- Do not collapse multiple target tables into one vague paragraph; list them separately when possible.
- For multi-DOCX output, `structured_facts.json` should list `documents`, include source provenance on facts, and preserve per-document extracted CSV paths under `extracted/doc_###_<name>/`.

## Delayed Header Tables

Some embedded Excel sheets start with explanatory rows before the real header. Scan the first rows for recognizable headers instead of assuming row 1 is the header.

- Skip preamble rows like `报表路由`, `数据源表`, `数据表：qas_*`, `计算频率`, and `数据粒度`.
- Treat rows containing `字段key / 字段名称 / 字段类型` as target field dictionaries even when they appear after preamble text.
- Preserve the preamble text as evidence. If it contains `数据表：qas_*`, use that declared table to match the field dictionary to Target Management or physical ClickHouse targets.
- Treat `字段公式`, `数据源+字段公式`, and longer headers containing both `数据源` and `字段公式` as calculation-rule evidence.

## Recognized COT Sync Matrices

For COT yearly sync docs, detect these embedded Excel shapes:

- Report list: headers like `序号`, `业务描述`, `hbase 表`, `Hbase数据范围`, `clickhouse表`.
- Data Utilization names: headers like `Name`, `Description`.
- Target mapping: headers like `Data Utilization Name`, `catalog`, `hbase_target前缀`, `clickhouse_target前缀`.
- Pipeline schedules: headers like `Data Utilization Name`, `task1 name`, `定时同步时间`, `pipeline前缀`.
- Field dictionaries: headers like `字段`, `字段描述`, `字段类型`, `字段类型(mysql)`.
- Field dictionary sheets are often embedded near正文 headings such as `sixzhen_gps_distance 进店与拍照距离收集报表`. Use the embedding object's nearby正文 context to map a field dictionary to a Data Utilization name before falling back to embedded-sheet order.
- Do not rely on Data Utilization order alone. Some COT docs omit, move, or regroup field dictionaries, so order-only matching can shift later dictionaries to the wrong table.
- A COT matrix row named `zo_bysku_detail_p` or containing `bySKU` remains a normal table-sync signal by itself. Route to `bysku_report_pipeline` only when separate evidence proves SKU-family calculation work such as NPD/B5/新品 outputs, SKU config parameters, prepare/calculation components, or rolling-retention rules.

The handoff to codegen should preserve source table, source range, target table, inferred Data Utilization name, field count, first fields, schedule, and any inferred mapping notes.

## Recognized Report Development Matrices

For DataEngine report docs, detect these embedded Excel shapes:

- Source matrix: headers like `位置`, `数据表名`, `数据表`, `取数范围`, `字段`, `关联、过滤信息`.
- Some supervisor-portal docs use `数据范围` instead of `取数范围` and omit explicit field/filter columns; still extract `位置`, `数据表名`, `数据表`, and the range.
- Physical ClickHouse target matrix: headers like `Description`, `Data Storage`, `Database`, `Table Name`.
- Word正文 or embedded target matrix: headers like `位置`, `数据库`, `数据表名`, `数据表`; for `Superview Clickhouse` rows, build physical tables such as `abnormal_monitor.qas_mw_visit_abnormal_store_daily`.
- Target Management: headers like `Data Utilization Name`, `Target Name`, `Target Description`, `Data Storage`.
- Catalog Basic Info: headers like `数据项`, `Title`, `IT Owner&Email`, `Biz Owner&Email`, `FE&Email`, `IT BP & Email`, `Data Engineer & Email`; preserve table names, titles, owner emails, FE, BP, and data engineer values for Pipeline Export catalog registration.
- Pipeline schedule: headers like `Data Utilization Name`, `Pipline_Name`, `task1 name`, `Description`, or `Pipeline Name` + `定时任务`.
- Target field logic: headers like `Key`/`字段 key`/`字段key`, `字段名称`/`字段名`, `数据源位置`, `数据表`, `数据源描述`/`来源库表`, `数据源对应的字段`/`来源字段`, `计算逻辑`.
- Word正文 field tables may contain an explanatory first row before the actual header row; the extractor should detect the real header row and skip the preamble.
- HBase physical target matrices may have headers like `位置`, `数据表`, `数据表名`; treat `Data Hub Hbase` plus a table such as `l1_cot.store_yield_grade_p` as a physical target, not a ClickHouse target.
- QAS-style Target Management may name logical targets as `clickhouse_qas_*` while physical tables are `abnormal_monitor.qas_*`; match them by stripping the `clickhouse_` prefix and comparing the table suffix.

## Recognized PRD Rule Matrices

For PRD documents that accompany DataEngine waterline docs, detect these business-rule shapes:

- Abnormal rule matrix: headers like `异常类型`, `判断规则`, `数据粒度`, `数据源`/`数据来源`, `产出数据表`.
- KPI matrix: headers like `KPI 名称`, `单位`, `数据来源底表`, `取值字段`, `汇总逻辑`.
- Manager summary matrix: headers like `汇总列`, `单位`, `数据来源底表`, `汇总逻辑`.

The handoff should preserve abnormal type, rule text, grain, source, output table, KPI name, source table/field, and aggregation logic. These facts should appear in `technical_design.md` under `KPI / Calculation Logic`.

The handoff to report codegen should preserve source storage type, source table/path, read range, source field list, join/filter notes, logical target names, physical HBase/ClickHouse/FS targets from Data Target text, field order, field-level calculation logic, EO/DMS-specific rules, and schedule rows.
