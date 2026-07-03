# Vehicle Verification Report Patterns

This reference is self-contained. If `prod_code_sample/vehicle_verification_202605221431` is present in the workspace, inspect it as optional style guidance, but do not depend on it.

Use this reference when a report has complex HBase + FS + ClickHouse data flow, multiple summary outputs, order-level detail, vehicle/customer mappings, or FS evidence retention.

## Key Shape

- `DataSource.run()` returns source maps plus `time_range`.
- `DataProcess.run()` returns one detail DataFrame and multiple summary DataFrames.
- `DataStorage.run()` writes several ClickHouse tables for the same period.
- `gateway/`, `hbase/`, and `fs/` are fixed platform packages. Preserve existing package files and keep vehicle-specific logic in `data_utils/` and `params_configs/`.
- Read `platform_client_usage.md` before generating or modifying code that uses `gateway/`, `fs/`, or `hbase`.

## DataSource Details

- HBase source tables and fields live in `params_configs/col_config.py`.
- FS source paths live in `params_configs/db_config.py`.
- Time range derives target period and start/end date from `mars_calendar`.
- HBase reads can use row ranges and row prefixes.
- FS source files may be copied locally into temp directories, read, then removed.
- Evidence files can be uploaded back to FS for auditability.
- For vehicle verification docs, source matrix rows map directly to HBase export config for `Data Hub Hbase` rows and FS directory config for `Gateway项目目录` / `Datahub 数据共享目录` rows.
- Preserve source matrix join/filter notes as implementation rules in `DataProcess`; do not leave them only as comments.
- Use the Gateway facade (`Client` or `GateWayClient`) to obtain `getHbaseClient(fs_root_dir=...)` and `getFsClient()`; do not call Gateway token/header/API helpers directly from report modules.

Additional generated DataSource rules:

- Derive `P`, compact `period`, `p_start_date`, and `p_end_date` from `l0_mdp.mars_calendar`.
- When `period` is supplied as `YYYYPnn` or `YYYYnn`, use that target period. When absent, use `current_date` or today to find the current period and select the previous period.
- HBase reads with `is_row_prefixs` / `row_prefixs` enabled should use prefixes `0` through `9`.
- FS paths containing `{Period}`, `{period}`, or `{P}` should be rendered from the resolved time range.
- Support injected `hbase_data`, `fs_data`, `hbase_client`, `fs_client`, or `gateway_client` for local verification without connecting to production.
- Default FS reads should use `exists/listdir/copy_to_local` plus local Pandas parsing and local temp cleanup.
- Default FS evidence writes should use `copy_from_local(..., overwrite=True)`.
- Do not generate `open`, `append`, `rename`, `mkdirs`, direct chunk upload, or direct `fs.operate_common` calls unless the existing project already uses that exact pattern.

## DataProcess Details

- Start with explicit data cleaning.
- Keep mapping references as properties or named DataFrames.
- Use vectorized pandas/numpy logic for large order/report data.
- Preserve no-order rows when the report requires full store coverage.
- Calculate detail first, then summary tables from the detail output.
- Use explicit `final_columns` for detail and summaries.
- Use helper aggregation functions when multiple summary grains share formulas.

## Vehicle Verification Output Rules

Use these rules when generating vehicle verification / vehicle reconcile reports. The code may be simpler than the reference, but these output semantics must be preserved.

### Source Field Rules

- `l0_dtr_order.t5_eo_erp_sales_order_line_p` needs order header, created/delivered time, status/source, sold-to, store code, category flag, amount fields, and both EO/BMP SKU fields.
- `l0_store_center.store_details_p` is the store base table. Keep all eligible stores by left-joining orders onto store detail.
- `l2_cot_exe_report.rpt_exe_sales_assess_channel` must rename `salesman_code` to `store_manager_code`.
- `l1_mdp.vehicle_info_p` requires at least `CustomerNo`, `PlateNo`, `PersonalNo`, `SalesmanNo`, `SalesmanNo2`, `VehicleStatus`, `DataType`, `ModifyDate`, `CreateDate`, and `PINNo`.
- `l0_customer_center.locust_customer_md` geography fields are `mars_geo_region_name`, `mars_geo_province_name`, `mars_geo_city_clusters_name`, and `mars_geo_city_name`; do not substitute store geography fields.
- If the source matrix omits a required field above, supplement the generated source config from these rules before writing `col_config.py`.
- If a source cell contains both a year-suffixed and non-suffixed sales assess table, prefer `l2_cot_exe_report.rpt_exe_sales_assess_channel` unless the dev doc explicitly selects the year-suffixed table.

### Cleaning And Mapping Rules

- EO rows: keep `order_status in ['4516', '4508']` and `bmp_eo_order_category == 'NDT'`.
- Exclude Chips/Cereals product rows using `prod_code` from product master; use EO SKU for EO orders and BMP SKU for ERP orders.
- Store rows: keep traditional channel and digital in presale/instock values.
- Customer master: keep `customer_type_code == 'DT'` and `division == '51'`.
- DMS rows: exclude Chips/Cereals category rows and rename DMS sub-distributor `code` to `customer_code`.
- Vehicle info: melt `PersonalNo`, `SalesmanNo`, and `SalesmanNo2` into one `store_manager_code`; keep non-empty codes; prefer running vehicles, then latest `ModifyDate`; if `ModifyDate` is empty, use `CreateDate`.
- Vehicle number: use `PlateNo`; for two/three-wheel dealer/sales vehicles with blank plate, use `PINNo`; normalize blank/`无`/`nan`/`None` to null.
- Missing vehicle tool defaults to `公共交通或其他`; missing vehicle status defaults to `空`; if vehicle number is blank, vehicle status must be `空`.

### Detail Output Rules

- Build EO and DMS order headers separately, then concatenate and left-join to store detail on store code.
- Preserve no-order stores in the detail table.
- Use the detail target dictionary field order exactly; do not rely on DataFrame natural column order.
- Assign `period` from target P and `year` from the first four chars of P.
- `is_difference_order`: compare `total_amount / order_gsv - 1`; flag `是` when ratio is greater than `0.4` or less than `-0.4`; no-order rows remain null.
- `order_difference_amount`: difference orders use `total_amount`, normal orders use `0`, no-order rows remain null.
- `is_48_deliver`: delivered within 48 hours; no-order rows remain null.
- `is_advance_order`: `order_advance_amount > 0`; no-order rows remain null.
- Customer type: sold-to in DT customer master is `经销商`; sold-to in DMS sub-distributor config is `二分商`.
- For DMS sub-distributors with `status == '1'`, map `order_customer_code/name` to `belongs_to_code/name`; otherwise keep sold-to.
- Final detail columns must exactly match the target field dictionary order.
- Generated vehicle code is incomplete if it builds the schemas but does not implement the EO/DMS header construction, store left join, vehicle/customer mapping, KPI calculations, and summary aggregations.
- The bundled scaffold generator should implement this `DataProcess` layer directly for vehicle verification plans.

### Summary Rules

- Presale summary scope: rows with orders where `(digital_district == 预售片区 and digital in [预售, 现售])` or `(digital_district == 现售片区 and digital == 预售)`.
- Presale summary produces two grains: by digital district and overall `预售片区+现售片区整体`.
- Use the presale and instock target dictionaries as separate final column lists; never generate one shared summary schema.
- Presale valid order metrics exclude difference orders: valid order count, valid 48h count, valid GSV, and valid advance amount use only `is_difference_order == 否`.
- `48_delivery_rate = valid_48_count / valid_order_count`, rounded to 4 decimals; zero denominator yields 0.
- `48_delivery_incentive_amount = order_gsv * 48_delivery_rate * 0.02` only when rate is at least `0.8`, otherwise null.
- Instock summary scope: rows with orders where `digital_district == 现售片区` and `digital == 现售`.
- Instock geography comes from sales assess channel by `store_manager_code`.
- Instock vehicle customer code should map from vehicle number first, then store manager code, and only for dealer vehicle types.
- `incentive_amount = order_gsv * 0.02`, rounded to 2 decimals.
- Fill final `vehicle_status` nulls with `空`.

### FS Evidence Rules

- Upload intermediate EO header and DMS header CSVs to FS evidence paths when the dev doc mentions data trace or Gateway project retention.
- Evidence upload failures should be logged, but should not silently change report output.
- HBase writes, when required, should use `insert_df(..., mode="import")` or `insert_file(..., sep="\x1D")`; do not generate `mode="insert"` or `HbaseClient.delete(...)`.

## DataStorage Details

- Keep a file map for temporary CSV names.
- Delete target old data by `period` before insert when period replacement is required.
- Write each output table separately.
- Clean temporary files in `finally`.
- New generated code should raise target write failures by default unless the user approves best-effort continuation.
- Generated vehicle storage may use direct DataFrame insertion instead of temporary CSV insertion when the platform client supports `insert_df` or `insert_dataframe`; preserve delete-by-period before insert.

## Common Confirmation Points

- Target period derivation: current P, previous P, or manual period.
- Whether no-order/no-data stores must remain in detail output.
- Product/category exclusion list.
- Customer and vehicle mapping priority.
- Summary grouping keys.
- Incentive/KPI formulas and denominator behavior.
- Delete condition for each ClickHouse target table.
- Whether FS evidence upload is required for EO/DMS intermediate headers.
