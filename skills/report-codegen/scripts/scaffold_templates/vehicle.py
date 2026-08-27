"""Vehicle-verification scaffold writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def vehicle_output_targets(plan: Dict[str, Any]) -> Dict[str, str]:
    targets = {"detail": "", "presale": "", "instock": ""}
    for output in plan.get("outputs", []):
        name = output.get("target_name", "")
        columns = set(output.get("final_columns", []))
        if "order_code" in columns and "vehicle_status" in columns:
            targets["detail"] = name
        elif "48_delivery_incentive_amount" in columns:
            targets["presale"] = name
        elif "incentive_amount" in columns and "vehicle_customer_code" in columns:
            targets["instock"] = name
    targets["detail"] = targets["detail"] or "clickhouse_vehicle_verify_detail"
    targets["presale"] = targets["presale"] or "clickhouse_vehicle_verify_sum_ps_fs"
    targets["instock"] = targets["instock"] or "clickhouse_vehicle_verify_sum_fs"
    return targets

def write_vehicle_data_process(target: Path, plan: Dict[str, Any]) -> None:
    targets = vehicle_output_targets(plan)
    content = f'''# coding: utf-8
from common_utils.all_modules import Dict, logger, np, pd
from params_configs.col_config import rename_map, target_table_columns


DETAIL_TARGET = {targets["detail"]!r}
PRESALE_TARGET = {targets["presale"]!r}
INSTOCK_TARGET = {targets["instock"]!r}
''' + r'''


def _blankish(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return series.isna() | text.isin(["", "无", "nan", "NaN", "None", "none"])


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def _ensure_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    for column in columns:
        if column not in df.columns:
            df[column] = np.nan
    return df


class DataProcess:
    """Build vehicle-verification outputs using requirement-defined joins and KPIs."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        logger.info("Initializing vehicle verification DataProcess")
        self.source_data = source_data
        self.time_range = time_range
        self.params = params
        self.period = str(time_range.get("period") or "").strip()
        self.P = str(time_range.get("P") or time_range.get("period") or "").strip()
        self._data: Dict[str, pd.DataFrame] = {}
        self.df_details = pd.DataFrame(columns=target_table_columns.get(DETAIL_TARGET, []))
        self.df_summary_presale = pd.DataFrame(columns=target_table_columns.get(PRESALE_TARGET, []))
        self.df_summary_instock = pd.DataFrame(columns=target_table_columns.get(INSTOCK_TARGET, []))

    def _source(self, key: str) -> pd.DataFrame:
        df = self.source_data.get(key)
        if df is None:
            return pd.DataFrame()
        df = df.copy()
        mapping = rename_map.get(key, {})
        if mapping:
            df = df.rename(columns=mapping)
        return df

    @property
    def eo_line(self):
        return self._data.get("eo_line", pd.DataFrame())

    @property
    def store_detail(self):
        return self._data.get("store_detail", pd.DataFrame())

    @property
    def sales_assess_channel(self):
        return self._data.get("sales_assess_channel", pd.DataFrame())

    @property
    def vehicle_info(self):
        return self._data.get("vehicle_info", pd.DataFrame())

    @property
    def customer_md(self):
        return self._data.get("customer_md", pd.DataFrame())

    @property
    def dms_order(self):
        return self._data.get("dms_order", pd.DataFrame())

    @property
    def dms_md(self):
        return self._data.get("dms_md", pd.DataFrame())

    @property
    def product_md(self):
        return self._data.get("product_md", pd.DataFrame())

    def data_clean(self):
        logger.info("transform_start step=vehicle_source_clean")
        eo_line = self._source("l0_dtr_order.t5_eo_erp_sales_order_line_p")
        eo_input_rows = len(eo_line)
        if not eo_line.empty:
            if {"order_status", "bmp_eo_order_category"}.issubset(eo_line.columns):
                # Requirement: only delivered/received NDT orders enter vehicle reconciliation.
                eo_line = eo_line[
                    eo_line["order_status"].astype(str).isin(["4516", "4508"])
                    & (eo_line["bmp_eo_order_category"].astype(str) == "NDT")
                ].copy()

            product_md = self._source("l0_product_center.locust_product_md")
            if not product_md.empty and {"subsegment", "prod_code"}.issubset(product_md.columns):
                exclude_skus = product_md.loc[
                    product_md["subsegment"].isin(["Chips", "Cereals", "薯片", "谷物"]),
                    "prod_code",
                ].dropna().astype(str).unique()
                if len(exclude_skus) and {"order_source", "mars_sku_no", "bmp_mars_sku_no"}.issubset(eo_line.columns):
                    # Requirement: EO and ERP orders identify the comparable SKU in different columns.
                    match_sku = np.where(
                        eo_line["order_source"].astype(str) == "EO订单",
                        eo_line["mars_sku_no"].astype(str),
                        np.where(
                            eo_line["order_source"].astype(str) == "ERP订单",
                            eo_line["bmp_mars_sku_no"].astype(str),
                            "",
                        ),
                    )
                    eo_line = eo_line[~np.isin(match_sku, exclude_skus)].copy()
            self._data["product_md"] = product_md
        else:
            self._data["product_md"] = self._source("l0_product_center.locust_product_md")
        self._data["eo_line"] = eo_line
        logger.info(
            "transform_complete step=vehicle_eo_filter input_rows={} output_rows={}",
            eo_input_rows,
            len(eo_line),
        )

        store_detail = self._source("l0_store_center.store_details_p")
        store_input_rows = len(store_detail)
        if not store_detail.empty:
            # Requirement: the report population is traditional-channel presale or current-sale stores.
            if "digital" in store_detail.columns:
                store_detail = store_detail[store_detail["digital"].isin(["预售", "现售"])].copy()
            if "channel_name" in store_detail.columns:
                store_detail = store_detail[store_detail["channel_name"] == "传统渠道"].copy()
        self._data["store_detail"] = store_detail
        logger.info(
            "transform_complete step=vehicle_store_scope input_rows={} output_rows={}",
            store_input_rows,
            len(store_detail),
        )

        self._data["sales_assess_channel"] = self._source("l2_cot_exe_report.rpt_exe_sales_assess_channel")
        self._data["vehicle_info"] = self._clean_vehicle_info(self._source("l1_mdp.vehicle_info_p"))

        customer_md = self._source("l0_customer_center.locust_customer_md")
        if not customer_md.empty:
            if "customer_type_code" in customer_md.columns:
                customer_md = customer_md[customer_md["customer_type_code"] == "DT"].copy()
            if "division" in customer_md.columns:
                customer_md = customer_md[customer_md["division"].astype(str) == "51"].copy()
        self._data["customer_md"] = customer_md

        dms_order = self.source_data.get("dms_order", pd.DataFrame()).copy()
        if not dms_order.empty and "category" in dms_order.columns:
            dms_order = dms_order[~dms_order["category"].isin(["Chips", "Cereals", "薯片", "谷物"])].copy()
        self._data["dms_order"] = dms_order

        dms_md = self.source_data.get("dms_md", pd.DataFrame()).copy()
        if not dms_md.empty and "code" in dms_md.columns:
            dms_md = dms_md.rename(columns={"code": "customer_code"})
        self._data["dms_md"] = dms_md
        return self

    def _clean_vehicle_info(self, df_vehicle_raw: pd.DataFrame) -> pd.DataFrame:
        columns = ["store_manager_code", "vehicle_tool", "vehicle_num", "vehicle_status", "customer_code"]
        if df_vehicle_raw.empty:
            return pd.DataFrame(columns=columns)

        id_vars = ["customer_code", "vehicle_status", "vehicle_tool", "vehicle_num", "PINNo", "ModifyDate", "CreateDate"]
        value_vars = ["store_manager_code", "SalesmanNo", "SalesmanNo2"]
        df_vehicle_raw = _ensure_columns(df_vehicle_raw, id_vars + value_vars)

        df_melt = pd.melt(
            df_vehicle_raw,
            id_vars=id_vars,
            value_vars=value_vars,
            var_name="source_role",
            value_name="final_manager_code",
        )
        df_melt = df_melt.rename(columns={"final_manager_code": "store_manager_code"}).drop(columns=["source_role"])
        df_melt = df_melt[~_blankish(df_melt["store_manager_code"])].copy()
        if df_melt.empty:
            return pd.DataFrame(columns=columns)

        df_melt["is_running"] = np.where(df_melt["vehicle_status"].astype(str).str.strip() == "行驶", 1, 0)
        modify_text = df_melt["ModifyDate"].astype(str).str.strip()
        df_melt["ModifyDate"] = np.where(
            modify_text.isin(["", "nan", "NaN", "None", "none"]),
            df_melt["CreateDate"],
            df_melt["ModifyDate"],
        )
        df_melt["ModifyDate"] = pd.to_datetime(df_melt["ModifyDate"], errors="coerce")
        df_melt = df_melt.sort_values(
            by=["store_manager_code", "is_running", "ModifyDate"],
            ascending=[True, False, False],
        )
        df_unique = df_melt.drop_duplicates(subset=["store_manager_code"], keep="first").copy()

        plate = df_unique["vehicle_num"].astype(str).str.strip()
        pin = df_unique["PINNo"].astype(str).str.strip()
        no_plate_mask = (plate == "") | (plate == "无") | plate.str.lower().isin(["nan", "none"])
        three_wheel_mask = df_unique["vehicle_tool"].isin(["经销商三轮车", "销售三轮车"])
        df_unique["vehicle_num"] = np.where(no_plate_mask & three_wheel_mask, pin, plate)
        df_unique["vehicle_num"] = df_unique["vehicle_num"].replace(
            {"": np.nan, "无": np.nan, "nan": np.nan, "NaN": np.nan, "None": np.nan, "none": np.nan}
        )
        return df_unique[columns].reset_index(drop=True)

    def _get_eo_orders_only(self) -> pd.DataFrame:
        columns = [
            "code", "order_code", "order_created_time", "order_delivered_time",
            "sold_to_code", "sold_to_name", "order_source",
            "total_amount", "order_gsv", "order_advance_amount",
        ]
        if self.eo_line.empty:
            return pd.DataFrame(columns=columns)
        header = _ensure_columns(
            self.eo_line.copy(),
            [
                "mars_store_code", "mars_order_header_no", "order_created_at", "first_complete_time",
                "sold_to_code", "sold_to_name", "original_amount", "pt_sum", "coupon_amt",
            ],
        )
        df = pd.DataFrame(
            {
                "code": header["mars_store_code"],
                "order_code": header["mars_order_header_no"],
                "order_created_time": pd.to_datetime(header["order_created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_time": pd.to_datetime(header["first_complete_time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "sold_to_code": header["sold_to_code"],
                "sold_to_name": header["sold_to_name"],
                "order_source": "EO订单",
                "total_amount": _to_number(header["original_amount"]),
                "order_gsv": _to_number(header["pt_sum"]),
                "order_advance_amount": _to_number(header["coupon_amt"]),
            }
        )
        group_keys = [
            "code", "order_code", "order_created_time", "order_delivered_time",
            "sold_to_code", "sold_to_name", "order_source",
        ]
        df = df.groupby(group_keys, as_index=False, dropna=False)[["total_amount", "order_gsv", "order_advance_amount"]].sum()
        for column in ["total_amount", "order_gsv", "order_advance_amount"]:
            df[column] = df[column].round(2)
        return df

    def _get_dms_orders_only(self) -> pd.DataFrame:
        columns = [
            "code", "order_code", "order_created_time", "order_delivered_time", "marsk",
            "reason_for_reversal", "total_amount", "order_gsv", "order_advance_amount",
            "sold_to_code", "sold_to_name", "order_source",
        ]
        if self.dms_order.empty:
            return pd.DataFrame(columns=columns)
        df_dms = _ensure_columns(
            self.dms_order.copy(),
            [
                "org_mars_order_header_no", "org_dtr_created_at", "update_time", "marsk",
                "reason_for_reversal", "supplier_code", "supplier_name", "mars_store_code",
                "org_dtr_source_type", "qct_total", "sales_amount", "org_coupon_amt",
            ],
        )
        amount_cols = ["qct_total", "sales_amount", "org_coupon_amt"]
        for column in amount_cols:
            df_dms[column] = _to_number(df_dms[column])
        group_keys = [
            "org_mars_order_header_no", "org_dtr_created_at", "update_time", "marsk",
            "reason_for_reversal", "supplier_code", "supplier_name", "mars_store_code",
            "org_dtr_source_type",
        ]
        df_header = df_dms.groupby(group_keys, as_index=False, dropna=False)[amount_cols].sum()
        marsk = np.select(
            [df_header["marsk"].astype(str) == "0", df_header["marsk"].astype(str) == "1"],
            ["新增单", "冲销单"],
            default=df_header["marsk"].astype(str),
        )
        order_source = np.where(df_header["org_dtr_source_type"].astype(str) == "0", "EO订单", "ERP订单")
        return pd.DataFrame(
            {
                "code": df_header["mars_store_code"],
                "order_code": df_header["org_mars_order_header_no"],
                "order_created_time": pd.to_datetime(df_header["org_dtr_created_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_time": pd.to_datetime(df_header["update_time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S"),
                "marsk": marsk,
                "reason_for_reversal": df_header["reason_for_reversal"],
                "total_amount": df_header["qct_total"].round(2),
                "order_gsv": df_header["sales_amount"].round(2),
                "order_advance_amount": df_header["org_coupon_amt"].round(2),
                "sold_to_code": df_header["supplier_code"],
                "sold_to_name": df_header["supplier_name"],
                "order_source": order_source,
            }
        )

    def combine_all_orders(self):
        logger.info("Build detail table from store base and order streams")
        eo_orders = self._get_eo_orders_only()
        dms_orders = self._get_dms_orders_only()
        non_empty = [df for df in [eo_orders, dms_orders] if not df.empty]
        all_orders = pd.concat(non_empty, axis=0, ignore_index=True, sort=False) if non_empty else pd.DataFrame(columns=["code"])
        base = self.store_detail.copy()
        if base.empty:
            base = pd.DataFrame(columns=["code"])
        # Requirement: store scope owns output coverage, including stores with no matching order.
        self.df_details = pd.merge(base, all_orders, on="code", how="left")
        logger.info(
            "transform_complete step=vehicle_order_join stores={} orders={} output_rows={}",
            len(base),
            len(all_orders),
            len(self.df_details),
        )
        period_value = self.P or self.period
        self.df_details["period"] = period_value
        self.df_details["year"] = str(period_value)[:4]
        return self

    def combine_sales_assess(self):
        if self.sales_assess_channel.empty or self.df_details.empty:
            return self
        assess = _ensure_columns(
            self.sales_assess_channel.copy(),
            ["store_manager_code", "salesman_type", "sale_role"],
        )[["store_manager_code", "salesman_type", "sale_role"]].drop_duplicates("store_manager_code")
        self.df_details = pd.merge(
            self.df_details.drop(columns=["salesman_type", "sale_role"], errors="ignore"),
            assess,
            on="store_manager_code",
            how="left",
        )
        return self

    def combine_vehicle_info(self):
        if self.df_details.empty:
            return self
        if self.vehicle_info.empty:
            self.df_details["vehicle_tool"] = "公共交通或其他"
            self.df_details["vehicle_num"] = np.nan
            self.df_details["vehicle_status"] = "空"
            return self
        vehicle_ref = self.vehicle_info[["store_manager_code", "vehicle_tool", "vehicle_num", "vehicle_status"]]
        self.df_details = pd.merge(self.df_details, vehicle_ref, on="store_manager_code", how="left")
        self.df_details["vehicle_tool"] = self.df_details["vehicle_tool"].fillna("公共交通或其他")
        self.df_details["vehicle_status"] = self.df_details["vehicle_status"].fillna("空")
        if "vehicle_num" in self.df_details.columns:
            self.df_details.loc[_blankish(self.df_details["vehicle_num"]), "vehicle_status"] = "空"
        return self

    def calculate_kpi(self):
        if self.df_details.empty:
            return self
        df = self.df_details
        df = _ensure_columns(df, ["order_code", "total_amount", "order_gsv", "order_advance_amount", "sold_to_code", "sold_to_name"])
        order_empty = _blankish(df["order_code"])
        total_amount = _to_number(df["total_amount"])
        order_gsv = _to_number(df["order_gsv"])
        ratio = np.round(np.divide(total_amount, order_gsv, out=np.zeros(len(df)), where=order_gsv.to_numpy() != 0) - 1, 4)
        is_diff = (ratio > 0.4) | (ratio < -0.4)
        df["is_difference_order"] = np.where(order_empty, None, np.where(is_diff, "是", "否"))
        df["order_difference_amount"] = np.where(order_empty, np.nan, np.where(is_diff, total_amount, 0))

        start_time = pd.to_datetime(df.get("order_created_time"), errors="coerce")
        end_time = pd.to_datetime(df.get("order_delivered_time"), errors="coerce")
        duration_hours = (end_time - start_time).dt.total_seconds() / 3600
        df["is_48_deliver"] = np.where(order_empty, None, np.where((duration_hours < 48) & duration_hours.notna(), "是", "否"))
        df["is_advance_order"] = np.where(order_empty, None, np.where(_to_number(df["order_advance_amount"]) > 0, "是", "否"))

        dt_codes = self.customer_md["customer_code"].dropna().unique() if "customer_code" in self.customer_md.columns else []
        d2_codes = self.dms_md["customer_code"].dropna().unique() if "customer_code" in self.dms_md.columns else []
        sold_to = df["sold_to_code"]
        df["customer_type"] = np.select(
            [np.isin(sold_to, dt_codes), np.isin(sold_to, d2_codes)],
            ["经销商", "二分商"],
            default=None,
        )
        df["order_customer_code"] = df["sold_to_code"]
        df["order_customer_name"] = df["sold_to_name"]
        if not self.dms_md.empty and {"customer_code", "status", "belongs_to_code", "belongs_to_name"}.issubset(self.dms_md.columns):
            valid_rel = self.dms_md[self.dms_md["status"].astype(str) == "1"].drop_duplicates("customer_code")
            code_map = valid_rel.set_index("customer_code")["belongs_to_code"]
            name_map = valid_rel.set_index("customer_code")["belongs_to_name"]
            d2_mask = df["customer_type"] == "二分商"
            mapped_code = df["sold_to_code"].map(code_map)
            mapped_name = df["sold_to_code"].map(name_map)
            df["order_customer_code"] = np.where(d2_mask & mapped_code.notna(), mapped_code, df["order_customer_code"])
            df["order_customer_name"] = np.where(d2_mask & mapped_name.notna(), mapped_name, df["order_customer_name"])
        self.df_details = df
        return self

    def finalize_detail(self):
        for column in target_table_columns.get(DETAIL_TARGET, []):
            if column not in self.df_details.columns:
                self.df_details[column] = np.nan
        self.df_details = self.df_details.reindex(columns=target_table_columns.get(DETAIL_TARGET, []))
        return self

    def calculate_summary_presale(self):
        final_columns = target_table_columns.get(PRESALE_TARGET, [])
        if self.df_details.empty:
            self.df_summary_presale = pd.DataFrame(columns=final_columns)
            return self
        df_base = self.df_details[~_blankish(self.df_details["order_code"])].copy()
        if df_base.empty:
            self.df_summary_presale = pd.DataFrame(columns=final_columns)
            return self

        if not self.customer_md.empty and "customer_code" in self.customer_md.columns:
            cust_ref = self.customer_md.drop_duplicates("customer_code").set_index("customer_code")
            geo_map = {
                "mars_geo_region_name": "customer_region_name",
                "mars_geo_province_name": "customer_province_name",
                "mars_geo_city_clusters_name": "customer_city_cluster_name",
                "mars_geo_city_name": "customer_city_name",
            }
            for src, target in geo_map.items():
                if src in cust_ref.columns:
                    df_base[target] = df_base["order_customer_code"].map(cust_ref[src])

        def aggregate(target_df: pd.DataFrame, group_keys: list, district_label=None) -> pd.DataFrame:
            target_df = target_df.copy()
            for key in group_keys:
                if key not in target_df.columns:
                    target_df[key] = np.nan
            normal_mask = target_df["is_difference_order"] == "否"
            target_df["valid_order_cnt"] = np.where(normal_mask, 1, 0)
            target_df["valid_48_cnt"] = np.where(normal_mask & (target_df["is_48_deliver"] == "是"), 1, 0)
            target_df["valid_gsv"] = np.where(normal_mask, _to_number(target_df["order_gsv"]), 0)
            target_df["valid_advance"] = np.where(normal_mask, _to_number(target_df["order_advance_amount"]), 0)
            target_df["presale_store"] = np.where(target_df["digital"] == "预售", target_df["code"], np.nan)
            target_df["instock_store"] = np.where(target_df["digital"] == "现售", target_df["code"], np.nan)
            result = target_df.groupby(group_keys, as_index=False, dropna=False).agg(
                {
                    "code": "nunique",
                    "presale_store": "nunique",
                    "instock_store": "nunique",
                    "total_amount": "sum",
                    "order_difference_amount": "sum",
                    "valid_order_cnt": "sum",
                    "valid_48_cnt": "sum",
                    "valid_gsv": "sum",
                    "valid_advance": "sum",
                }
            )
            result["48_delivery_rate"] = (result["valid_48_cnt"] / result["valid_order_cnt"].replace(0, np.nan)).fillna(0).round(4)
            result["order_gsv"] = result["valid_gsv"].round(2)
            result["order_advance_amount"] = result["valid_advance"].round(2)
            result["total_amount"] = result["total_amount"].round(2)
            result["order_difference_amount"] = result["order_difference_amount"].round(2)
            result["48_delivery_incentive_amount"] = np.where(
                result["48_delivery_rate"] >= 0.8,
                (result["order_gsv"] * result["48_delivery_rate"] * 0.02).round(2),
                np.nan,
            )
            result = result.rename(
                columns={
                    "code": "store_count_sys",
                    "presale_store": "store_num_cheetah",
                    "instock_store": "store_num_lbcx",
                }
            )
            if district_label:
                result["digital_district"] = district_label
            return result

        scope = (
            ((df_base["digital_district"] == "预售片区") & df_base["digital"].isin(["预售", "现售"]))
            | ((df_base["digital_district"] == "现售片区") & (df_base["digital"] == "预售"))
        )
        base_keys = [
            "year", "period", "sold_to_code", "sold_to_name", "order_customer_code", "order_customer_name",
            "channel_name", "rtm_channel_name", "customer_region_name", "customer_province_name",
            "customer_city_cluster_name", "customer_city_name",
        ]
        result_1 = aggregate(df_base[scope], base_keys + ["digital_district"])
        result_2 = aggregate(df_base[scope], base_keys, district_label="预售片区+现售片区整体")
        self.df_summary_presale = pd.concat([result_1, result_2], axis=0, ignore_index=True).reindex(columns=final_columns)
        return self

    def calculate_summary_instock(self):
        final_columns = target_table_columns.get(INSTOCK_TARGET, [])
        if self.df_details.empty:
            self.df_summary_instock = pd.DataFrame(columns=final_columns)
            return self
        scope = (
            (self.df_details["digital_district"] == "现售片区")
            & (self.df_details["digital"] == "现售")
            & (~_blankish(self.df_details["order_code"]))
        )
        df_scope = self.df_details[scope].copy()
        if df_scope.empty:
            self.df_summary_instock = pd.DataFrame(columns=final_columns)
            return self

        if not self.sales_assess_channel.empty:
            assess = _ensure_columns(
                self.sales_assess_channel.copy(),
                ["store_manager_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"],
            )[["store_manager_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"]].drop_duplicates("store_manager_code")
            assess = assess.rename(
                columns={
                    "mars_region_name": "salesman_region_name",
                    "mars_province_name": "salesman_province_name",
                    "mars_city_cluster_name": "salesman_city_cluster_name",
                    "mars_city_name": "salesman_city_name",
                }
            )
            df_scope = pd.merge(df_scope, assess, on="store_manager_code", how="left")

        if not self.vehicle_info.empty:
            valid_vehicle = self.vehicle_info.dropna(subset=["customer_code"]).copy()
            if not valid_vehicle.empty:
                valid_vehicle["vehicle_num"] = valid_vehicle["vehicle_num"].replace(["无", ""], np.nan)
                by_num = valid_vehicle.dropna(subset=["vehicle_num"]).drop_duplicates("vehicle_num").set_index("vehicle_num")["customer_code"]
                by_mgr = valid_vehicle.dropna(subset=["store_manager_code"]).drop_duplicates("store_manager_code").set_index("store_manager_code")["customer_code"]
                customer_by_num = df_scope["vehicle_num"].map(by_num) if "vehicle_num" in df_scope.columns else pd.Series(np.nan, index=df_scope.index)
                customer_by_mgr = df_scope["store_manager_code"].map(by_mgr) if "store_manager_code" in df_scope.columns else pd.Series(np.nan, index=df_scope.index)
                candidate_code = customer_by_num.combine_first(customer_by_mgr)
                dealer_vehicle = df_scope["vehicle_tool"].isin(["经销商四轮车", "经销商二轮车", "经销商三轮车"])
                df_scope["vehicle_customer_code"] = np.where(dealer_vehicle & candidate_code.notna(), candidate_code, None)
                if not self.customer_md.empty and {"customer_code", "name"}.issubset(self.customer_md.columns):
                    name_map = self.customer_md.drop_duplicates("customer_code").set_index("customer_code")["name"]
                    df_scope["vehicle_customer_name"] = df_scope["vehicle_customer_code"].map(name_map)

        group_keys = [
            "year", "period", "salesman_region_name", "salesman_province_name", "salesman_city_cluster_name",
            "salesman_city_name", "digital_district", "store_manager_code", "store_manager_name", "salesman_type",
            "sale_role", "channel_name", "rtm_channel_name", "digital", "vehicle_tool", "vehicle_num",
            "vehicle_status", "vehicle_customer_code", "vehicle_customer_name",
        ]
        for key in group_keys:
            if key not in df_scope.columns:
                df_scope[key] = np.nan
        self.df_summary_instock = df_scope.groupby(group_keys, as_index=False, dropna=False).agg(
            {"code": "nunique", "total_amount": "sum", "order_gsv": "sum", "order_advance_amount": "sum"}
        )
        self.df_summary_instock = self.df_summary_instock.rename(columns={"code": "store_count_sys"})
        self.df_summary_instock["incentive_amount"] = (_to_number(self.df_summary_instock["order_gsv"]) * 0.02).round(2)
        for column in ["total_amount", "order_gsv", "order_advance_amount"]:
            self.df_summary_instock[column] = _to_number(self.df_summary_instock[column]).round(2)
        self.df_summary_instock = self.df_summary_instock.reindex(columns=final_columns)
        return self

    def handle_missing_values(self):
        for column in ["order_source", "vehicle_status", "marsk"]:
            if column in self.df_details.columns:
                self.df_details[column] = self.df_details[column].fillna("空")
        if "vehicle_status" in self.df_summary_instock.columns:
            self.df_summary_instock["vehicle_status"] = self.df_summary_instock["vehicle_status"].fillna("空")
        return self

    def run(self) -> Dict[str, pd.DataFrame]:
        (
            self.data_clean()
            .combine_all_orders()
            .combine_sales_assess()
            .combine_vehicle_info()
            .calculate_kpi()
            .finalize_detail()
            .calculate_summary_instock()
            .calculate_summary_presale()
            .handle_missing_values()
        )
        return {
            DETAIL_TARGET: self.df_details,
            PRESALE_TARGET: self.df_summary_presale,
            INSTOCK_TARGET: self.df_summary_instock,
        }
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")
