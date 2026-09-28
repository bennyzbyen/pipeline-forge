# COT 2026 historical sample observations

Scope: COT 2026 captured sample only. Status: historical comparison, not current-task confirmation. Source: the original COT Sync Patterns production-calibration section; no new production verification is claimed here.

Preserve these observations for comparisons. Require current task evidence before incorporating any mapping, source group or truncate mode into executable configuration. A matching table name alone is insufficient.

- `supervisor_assist_visit` maps to `v_supervisor_assist_visit_2026`.
- `rpt_exe_sales_assess_channel` maps to `rpt_exe_sales_assess_channel_2022`.
- `rpt_exe_visit_planning_execute_rate` is without-period despite having a `period` field.
- `supervisor_remake_remark`, `v_supervisor_assist_visit_2026`, `rpt_exe_sales_assess_channel_2022`, and `freshness_report` are with-period execution-family examples.
- `cot_gps_tracking_report`, `cot_gps_tracking_report_by_week`, `supervisor_remake_remark`, and `v_supervisor_assist_visit_2026` use the `store_report` source group.
- `rpt_exe_store_past_will` and `wechat_authorization_info` use the legacy `cot_report` ClickHouse database.
- The sample truncates ClickHouse and HBase for `wechat_authorization_info`; this observation never authorizes current-task truncation.
- That sample passes bare `clickhouse_table` names and keeps database prefixes in configuration.

Verification after adoption: check each affected table through the manifest verifier, then fake-runtime tests for its confirmed write scope, failure and watermark behavior. Record the applicability reason and corresponding validation in the existing handoff.

The scaffold applies historical mapping/classification overrides only when facts explicitly contain `cot_historical_profile = {"name": "cot_2026", "confirmed": true, "evidence": "current-task scope evidence"}`. Do not synthesize this confirmation from a name or year. Truncation is separate: each table requires `truncate_contract = {"confirmed": true, "evidence": "current-task write-scope evidence", "targets": ["clickhouse", "hbase"]}` with only the actually authorized targets. The profile alone never enables truncation. Cluster selection comes from the declared environment profile; an undeclared cluster remains a placeholder.
