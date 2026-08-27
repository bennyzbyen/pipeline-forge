"""Supervisor Portal scaffold writers."""

from __future__ import annotations

from pathlib import Path


def write_supervisor_portal_data_process(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, np, pd
from params_configs.col_config import target_table_columns


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _ensure_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    for column in columns:
        if column not in df.columns:
            df[column] = np.nan
    return df


class DataProcess:
    """Build supervisor-portal outputs while preserving report grain and defaults."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params
        self.current_date = str(time_range.get("current_date") or "")
        self.p_start_time = str(time_range.get("p_start_time") or self.current_date)
        self.p_end_time = str(time_range.get("p_end_time") or self.current_date)

    def _source(self, *names: str) -> pd.DataFrame:
        for name in names:
            if name in self.source_data:
                return self.source_data[name].copy()
        for key, value in self.source_data.items():
            key_tail = str(key).split(".")[-1]
            for name in names:
                if key_tail == name or str(key).endswith(name):
                    return value.copy()
        return pd.DataFrame()

    def _previous(self, name: str, columns: list) -> pd.DataFrame:
        injected = self.params.get(name)
        if isinstance(injected, pd.DataFrame):
            df = injected.copy()
            for column in columns:
                if column not in df.columns:
                    df[column] = np.nan
            return df[columns].copy()
        return pd.DataFrame(columns=columns)

    def _safe_divide(self, numerator, denominator):
        # Requirement: zero or missing denominators yield 0 and KPI values use four decimals.
        denominator = _to_number(denominator)
        numerator = _to_number(numerator)
        return (numerator / denominator.replace(0, np.nan)).fillna(0).round(4)

    def _base_store(self) -> pd.DataFrame:
        df = self._source("topic_supervisor_portal.store_details", "store_details")
        if df.empty:
            return pd.DataFrame(columns=["store_code"])
        if "code" in df.columns and "store_code" not in df.columns:
            df = df.rename(columns={"code": "store_code"})
        if "cover_mode" in df.columns:
            # Requirement: only the three documented sugar-and-chocolate coverage modes are in scope.
            cover = df["cover_mode"].astype(str)
            df = df[
                cover.str.contains("糖巧固定覆盖", na=False)
                | cover.str.contains("糖巧非固定覆盖", na=False)
                | cover.str.contains("糖巧线路外覆盖", na=False)
            ].copy()
        if {"state", "closed_date"}.issubset(df.columns):
            # Requirement: closed stores remain visible only when closure is after the R2P boundary.
            r2p = str(self.time_range.get("r2p") or "")
            state_text = df["state"].astype(str)
            df = df[(state_text == "1") | ((state_text == "0") & (df["closed_date"].astype(str) > r2p))].copy()
        return df.drop_duplicates("store_code") if "store_code" in df.columns else df

    def _product_dimensions(self) -> pd.DataFrame:
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if product.empty:
            return pd.DataFrame({"segment": ["空"], "subsegment": ["空"]})
        product = _ensure_columns(product, ["segment", "subsegment"])
        segment = self.params.get("segment")
        subsegment = self.params.get("subsegment")
        if segment:
            product = product[product["segment"].isin(segment if isinstance(segment, list) else [segment])]
        if subsegment:
            product = product[product["subsegment"].isin(subsegment if isinstance(subsegment, list) else [subsegment])]
        dims = product[["segment", "subsegment"]].drop_duplicates().reset_index(drop=True)
        if dims.empty:
            dims = pd.DataFrame(columns=["segment", "subsegment"])
        dims.loc[len(dims)] = ["空", "空"]
        return dims.drop_duplicates().reset_index(drop=True)

    def _today_sales(self) -> pd.Series:
        orders = self._source("topic_supervisor_portal.eo_order_detail_pool", "eo_order_detail_pool")
        if orders.empty:
            return pd.Series(dtype=float, name="today_sales")
        orders = _ensure_columns(orders, ["store_code", "create_time", "order_state", "pt_sum"])
        orders["create_time"] = pd.to_datetime(orders["create_time"], errors="coerce")
        start = pd.to_datetime(self.current_date)
        end = start.replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["create_time"] >= start)
            & (orders["create_time"] <= end)
            & (~orders["order_state"].astype(str).isin(["4509", "4512", "已取消", "已拒收"]))
        ].copy()
        valid["pt_sum"] = _to_number(valid["pt_sum"])
        result = valid.groupby("store_code")["pt_sum"].sum()
        result.name = "today_sales"
        return result

    def _pty_sales(self) -> pd.Series:
        orders = self._source("l0_eo.order_details_sync", "l0_eo.order_detail_sync", "order_details_sync", "order_detail_sync")
        if orders.empty:
            return pd.Series(dtype=float, name="pty_sales")
        if "customers_code" in orders.columns and "store_code" not in orders.columns:
            orders = orders.rename(columns={"customers_code": "store_code"})
        orders = _ensure_columns(orders, ["store_code", "order_date", "order_status", "order_pt_sum"])
        orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        end = pd.to_datetime(self.time_range.get("yester_day") or self.current_date).replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["order_date"] >= start)
            & (orders["order_date"] <= end)
            & (~orders["order_status"].astype(str).isin(["已取消", "已拒收", "4509", "4512"]))
        ].copy()
        valid["order_pt_sum"] = _to_number(valid["order_pt_sum"])
        result = valid.groupby("store_code")["order_pt_sum"].sum()
        result.name = "pty_sales"
        return result

    def _today_sales_by_product(self) -> pd.DataFrame:
        orders = self._source("topic_supervisor_portal.eo_order_detail_pool", "eo_order_detail_pool")
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if orders.empty:
            return pd.DataFrame(columns=["store_code", "segment", "subsegment", "today_sales"])
        orders = _ensure_columns(orders, ["store_code", "create_time", "order_state", "pt_sum", "product_code"])
        product = _ensure_columns(product, ["prod_code", "segment", "subsegment"])
        orders["create_time"] = pd.to_datetime(orders["create_time"], errors="coerce")
        start = pd.to_datetime(self.current_date)
        end = start.replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["create_time"] >= start)
            & (orders["create_time"] <= end)
            & (~orders["order_state"].astype(str).isin(["4509", "4512", "已取消", "已拒收"]))
        ].copy()
        valid = valid.merge(product[["prod_code", "segment", "subsegment"]], left_on="product_code", right_on="prod_code", how="left")
        valid[["segment", "subsegment"]] = valid[["segment", "subsegment"]].fillna("空")
        valid["pt_sum"] = _to_number(valid["pt_sum"])
        return valid.groupby(["store_code", "segment", "subsegment"], dropna=False)["pt_sum"].sum().reset_index(name="today_sales")

    def _pty_sales_by_product(self) -> pd.DataFrame:
        orders = self._source("l0_eo.order_details_sync", "l0_eo.order_detail_sync", "order_details_sync", "order_detail_sync")
        product = self._source("l0_product_center.locust_product_md", "locust_product_md")
        if orders.empty:
            return pd.DataFrame(columns=["store_code", "segment", "subsegment", "pty_sales"])
        if "customers_code" in orders.columns and "store_code" not in orders.columns:
            orders = orders.rename(columns={"customers_code": "store_code"})
        product = _ensure_columns(product, ["prod_code", "segment", "subsegment"])
        orders = _ensure_columns(orders, ["store_code", "order_date", "order_status", "order_pt_sum", "product_std_code"])
        orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        end = pd.to_datetime(self.time_range.get("yester_day") or self.current_date).replace(hour=23, minute=59, second=59)
        valid = orders[
            (orders["order_date"] >= start)
            & (orders["order_date"] <= end)
            & (~orders["order_status"].astype(str).isin(["已取消", "已拒收", "4509", "4512"]))
        ].copy()
        valid = valid.merge(product[["prod_code", "segment", "subsegment"]], left_on="product_std_code", right_on="prod_code", how="left")
        valid[["segment", "subsegment"]] = valid[["segment", "subsegment"]].fillna("空")
        valid["order_pt_sum"] = _to_number(valid["order_pt_sum"])
        return valid.groupby(["store_code", "segment", "subsegment"], dropna=False)["order_pt_sum"].sum().reset_index(name="pty_sales")

    def _visit_flags(self):
        visit = self._source("topic_supervisor_portal.fts_store_visit_log", "fts_store_visit_log")
        if visit.empty:
            return pd.DataFrame(columns=["store_code", "today_is_visited"]), pd.Series(dtype=int, name="ptd_total_visits")
        if "store_id" in visit.columns and "store_code" not in visit.columns:
            visit = visit.rename(columns={"store_id": "store_code"})
        visit = _ensure_columns(visit, ["store_code", "created_timestamp", "status"])
        visit["created_timestamp"] = pd.to_datetime(visit["created_timestamp"], errors="coerce")
        today = pd.to_datetime(self.current_date)
        today_end = today.replace(hour=23, minute=59, second=59)
        p_start = pd.to_datetime(self.p_start_time)
        valid = visit[visit["status"].astype(str).isin(["2", "2.0"])].copy()
        today_df = valid[(valid["created_timestamp"] >= today) & (valid["created_timestamp"] <= today_end)]
        today_flag = pd.DataFrame({"store_code": today_df["store_code"].dropna().unique(), "today_is_visited": 1})
        ptd = valid[(valid["created_timestamp"] >= p_start) & (valid["created_timestamp"] <= today_end)].copy()
        ptd["visit_date"] = ptd["created_timestamp"].dt.date
        ptd_total = ptd[["store_code", "visit_date"]].drop_duplicates().groupby("store_code").size()
        ptd_total.name = "ptd_total_visits"
        return today_flag, ptd_total

    def _plan_flags(self):
        plan = self._source("l0_cot_visit.store_planning", "store_planning")
        exec_rate = self._source("l2_cot_exe_report.rpt_exe_visit_planning_execute_rate", "rpt_exe_visit_planning_execute_rate")
        today = pd.to_datetime(self.current_date).date()
        if not plan.empty:
            plan = _ensure_columns(plan, ["store_code", "planning_date", "user_segment"])
            if "user_segment" in plan.columns:
                plan = plan[plan["user_segment"].astype(str) == "MW"].copy()
            plan["planning_date"] = pd.to_datetime(plan["planning_date"], errors="coerce").dt.date
            today_plan = plan[plan["planning_date"] == today]
            today_flag = pd.DataFrame({"store_code": today_plan["store_code"].dropna().unique(), "today_is_visit_planned": 1})
        else:
            today_flag = pd.DataFrame(columns=["store_code", "today_is_visit_planned"])

        if exec_rate.empty:
            empty = pd.Series(dtype=int)
            empty.name = "pty_total_planned_visits"
            return today_flag, empty, empty.rename("pty_planned_visits_completed")
        exec_rate = _ensure_columns(exec_rate, ["store_code", "planning_date", "today_executed", "visit_emp_segment"])
        if "visit_emp_segment" in exec_rate.columns:
            exec_rate = exec_rate[exec_rate["visit_emp_segment"].astype(str) == "MW"].copy()
        exec_rate["planning_date"] = pd.to_datetime(exec_rate["planning_date"], errors="coerce")
        start = pd.to_datetime(self.p_start_time)
        yesterday = pd.to_datetime(self.time_range.get("yester_day") or self.current_date)
        scoped = exec_rate[(exec_rate["planning_date"] >= start) & (exec_rate["planning_date"] <= yesterday)].copy()
        total = scoped.groupby("store_code").size()
        total.name = "pty_total_planned_visits"
        completed = scoped[scoped["today_executed"].astype(str).isin(["1", "1.0"])].groupby("store_code").size()
        completed.name = "pty_planned_visits_completed"
        return today_flag, total, completed

    def _calculate_is_store_activated(self, df: pd.DataFrame) -> pd.DataFrame:
        df = _ensure_columns(df, ["rtm_channel_code", "channel_code", "store_channel_code"])
        cond1 = df["rtm_channel_code"].astype(str) == "FT-TT"
        cond2 = df["rtm_channel_code"].astype(str) == "WS"
        cond3 = (df["channel_code"].astype(str) == "MT") & (df["rtm_channel_code"].astype(str) == "FT-Non KA")
        cond4 = (df["store_channel_code"].astype(str) != "PlatformOwned") & (df["rtm_channel_code"].astype(str) == "O2O前置仓")
        df["is_store_activated"] = np.where(cond1 | cond2 | cond3 | cond4, 1, 0).astype(int)
        return df

    def _build_store(self) -> pd.DataFrame:
        df = self._base_store()
        if df.empty:
            return self._finalize("supervisor_portal_store", df)
        today_sales = self._today_sales()
        pty_sales = self._pty_sales()
        today_visited, ptd_total_visits = self._visit_flags()
        today_plan, pty_total_plans, pty_completed_plans = self._plan_flags()
        previous = self._previous("previous_store", ["store_code", "today_sales", "today_is_visit_planned", "today_is_visited", "today_order_placed"])
        if not previous.empty:
            previous = previous.rename(columns={
                "today_sales": "yesterday_sales",
                "today_is_visit_planned": "yesterday_is_visit_planned",
                "today_is_visited": "yesterday_is_visited",
                "today_order_placed": "yesterday_order_placed",
            })
            df = df.merge(previous, on="store_code", how="left")
        for series in [today_sales, pty_sales, ptd_total_visits, pty_total_plans, pty_completed_plans]:
            if not series.empty:
                df = df.merge(series.reset_index(), on="store_code", how="left")
        for flag_df in [today_visited, today_plan]:
            if not flag_df.empty:
                df = df.merge(flag_df, on="store_code", how="left")
        defaults = {
            "today_sales": 0,
            "yesterday_sales": 0,
            "pty_sales": 0,
            "today_is_visit_planned": 0,
            "today_is_visited": 0,
            "yesterday_is_visit_planned": 0,
            "yesterday_is_visited": 0,
            "pty_total_visits": 0,
            "pty_planned_visits_completed": 0,
            "pty_total_planned_visits": 0,
            "yesterday_order_placed": 0,
        }
        for column, value in defaults.items():
            if column not in df.columns:
                df[column] = value
            df[column] = _to_number(df[column])
        df["ptd_sales"] = _to_number(df["today_sales"]) + _to_number(df["pty_sales"])
        df["ptd_total_visits"] = _to_number(df["ptd_total_visits"])
        df["ptd_planned_visits_completed"] = np.where(
            (_to_number(df["today_is_visit_planned"]) == 1) & (_to_number(df["today_is_visited"]) == 1),
            _to_number(df["pty_planned_visits_completed"]) + 1,
            _to_number(df["pty_planned_visits_completed"]),
        )
        df["ptd_total_planned_visits"] = np.where(
            _to_number(df["today_is_visit_planned"]) == 1,
            _to_number(df["pty_total_planned_visits"]) + 1,
            _to_number(df["pty_total_planned_visits"]),
        )
        df = self._calculate_is_store_activated(df)
        df["today_order_placed"] = np.where(_to_number(df["today_sales"]) > 0, 1, 0)
        df["pty_order_placed"] = np.where(_to_number(df["pty_sales"]) > 0, 1, 0)
        df["ptd_orde_placed"] = np.where(_to_number(df["ptd_sales"]) > 0, 1, 0)
        return self._finalize("supervisor_portal_store", df)

    def _build_store_sales(self) -> pd.DataFrame:
        base = self._base_store()
        dims = self._product_dimensions()
        if base.empty:
            return self._finalize("supervisor_portal_store_sales", base)
        base = base.merge(dims, how="cross")
        previous = self._previous("previous_store_sales", ["store_code", "segment", "subsegment", "today_sales"])
        if not previous.empty:
            previous = previous.rename(columns={"today_sales": "yesterday_sales"})
            base = base.merge(previous, on=["store_code", "segment", "subsegment"], how="left")
        for df_sales in [self._today_sales_by_product(), self._pty_sales_by_product()]:
            if not df_sales.empty:
                base = base.merge(df_sales, on=["store_code", "segment", "subsegment"], how="left")
        for column in ["today_sales", "yesterday_sales", "pty_sales"]:
            if column not in base.columns:
                base[column] = 0
            base[column] = _to_number(base[column])
        base["ptd_sales"] = base["today_sales"] + base["pty_sales"]
        base = self._calculate_is_store_activated(base)
        return self._finalize("supervisor_portal_store_sales", base)

    def _aggregate_common(self, df: pd.DataFrame, group_keys: list, target_name: str) -> pd.DataFrame:
        if df.empty:
            return self._finalize(target_name, df)
        df = _ensure_columns(df, group_keys + [
            "state", "digital", "is_store_activated", "today_sales", "yesterday_sales", "pty_sales", "ptd_sales",
            "today_is_visited", "today_is_visit_planned", "yesterday_is_visited", "yesterday_is_visit_planned",
            "pty_total_visits", "pty_planned_visits_completed", "pty_total_planned_visits",
            "ptd_total_visits", "ptd_planned_visits_completed", "ptd_total_planned_visits",
            "today_order_placed", "yesterday_order_placed", "pty_order_placed", "ptd_orde_placed",
        ])
        active = _to_number(df["is_store_activated"]) == 1
        valid = df["state"].astype(str).isin(["1", "1.0"])
        digital = df["digital"].isin(["现售", "预售"])
        work = df.copy()
        work["_today_order_count"] = np.where(valid & active & digital & (_to_number(work["today_order_placed"]) == 1), 1, 0)
        work["_yesterday_order_count"] = np.where(valid & active & digital & (_to_number(work["yesterday_order_placed"]) == 1), 1, 0)
        work["_pty_order_count"] = np.where(valid & active & digital & (_to_number(work["pty_order_placed"]) == 1), 1, 0)
        work["_ptd_order_count"] = np.where(valid & active & digital & (_to_number(work["ptd_orde_placed"]) == 1), 1, 0)
        work["_today_digital_visit"] = np.where(valid & active & digital & (_to_number(work["today_is_visited"]) == 1), 1, 0)
        work["_yesterday_digital_visit"] = np.where(valid & active & digital & (_to_number(work["yesterday_is_visited"]) == 1), 1, 0)
        agg = work.groupby(group_keys, dropna=False).agg(
            today_sales=("today_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            yesterday_sales=("yesterday_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            pty_sales=("pty_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            ptd_sales=("ptd_sales", lambda x: _to_number(x[active.loc[x.index]]).sum()),
            today_visit_store_count=("today_is_visited", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            today_planned_visits_completed_store_count=("today_is_visited", lambda x: ((_to_number(x[valid.loc[x.index]]) == 1) & (_to_number(work.loc[x.index, "today_is_visit_planned"]) == 1)).sum()),
            today_visit_plan_store_count=("today_is_visit_planned", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            yesterday_visit_store_count=("yesterday_is_visited", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            yesterday_planned_visits_completed_store_count=("yesterday_is_visited", lambda x: ((_to_number(x[valid.loc[x.index]]) == 1) & (_to_number(work.loc[x.index, "yesterday_is_visit_planned"]) == 1)).sum()),
            yesterday_visit_plan_store_count=("yesterday_is_visit_planned", lambda x: (_to_number(x[valid.loc[x.index]]) == 1).sum()),
            pty_total_visits=("pty_total_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            pty_planned_visits_completed=("pty_planned_visits_completed", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            pty_total_planned_visits=("pty_total_planned_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_total_visits=("ptd_total_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_planned_visits_completed=("ptd_planned_visits_completed", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            ptd_total_planned_visits=("ptd_total_planned_visits", lambda x: _to_number(x[valid.loc[x.index]]).sum()),
            today_order_store_count=("_today_order_count", "sum"),
            yesterday_order_store_count=("_yesterday_order_count", "sum"),
            pty_order_store_count=("_pty_order_count", "sum"),
            ptd_order_store_count=("_ptd_order_count", "sum"),
            today_digital_visit_store_count=("_today_digital_visit", "sum"),
            yesterday_digital_visit_store_count=("_yesterday_digital_visit", "sum"),
            pty_digital_visit_store_count=("pty_total_visits", lambda x: _to_number(x[valid.loc[x.index] & active.loc[x.index] & digital.loc[x.index]]).sum()),
            ptd_digital_visit_store_count=("ptd_total_visits", lambda x: _to_number(x[valid.loc[x.index] & active.loc[x.index] & digital.loc[x.index]]).sum()),
        ).reset_index()
        agg["today_visit_plan_execution_rate"] = self._safe_divide(agg["today_planned_visits_completed_store_count"], agg["today_visit_plan_store_count"])
        agg["yesterday_visit_plan_execution_rate"] = self._safe_divide(agg["yesterday_planned_visits_completed_store_count"], agg["yesterday_visit_plan_store_count"])
        agg["pty_visit_plan_execution_rate"] = self._safe_divide(agg["pty_planned_visits_completed"], agg["pty_total_planned_visits"])
        agg["ptd_visit_plan_execution_rate"] = self._safe_divide(agg["ptd_planned_visits_completed"], agg["ptd_total_planned_visits"])
        agg["today_store_activation_rate"] = self._safe_divide(agg["today_order_store_count"], agg["today_digital_visit_store_count"])
        agg["yesterday_store_activation_rate"] = self._safe_divide(agg["yesterday_order_store_count"], agg["yesterday_digital_visit_store_count"])
        agg["pty_store_activation_rate"] = self._safe_divide(agg["pty_order_store_count"], agg["pty_digital_visit_store_count"])
        agg["ptd_store_activation_rate"] = self._safe_divide(agg["ptd_order_store_count"], agg["ptd_digital_visit_store_count"])
        return self._finalize(target_name, agg)

    def _aggregate_sales(self, df: pd.DataFrame, group_keys: list, target_name: str) -> pd.DataFrame:
        if df.empty:
            return self._finalize(target_name, df)
        df = _ensure_columns(df, group_keys + ["is_store_activated", "today_sales", "yesterday_sales", "pty_sales", "ptd_sales"])
        scoped = df[_to_number(df["is_store_activated"]) == 1].copy()
        result = scoped.groupby(group_keys, dropna=False).agg(
            today_sales=("today_sales", "sum"),
            yesterday_sales=("yesterday_sales", "sum"),
            pty_sales=("pty_sales", "sum"),
            ptd_sales=("ptd_sales", "sum"),
        ).reset_index()
        return self._finalize(target_name, result)

    def _user_information(self) -> pd.DataFrame:
        return self._finalize("user_information", self._source("l0_user_center.user_information", "user_information"))

    def _finalize(self, target_name: str, df: pd.DataFrame) -> pd.DataFrame:
        columns = target_table_columns.get(target_name, [])
        df = df.copy()
        for column in columns:
            if column not in df.columns:
                df[column] = np.nan
        final = df.reindex(columns=columns)
        logger.info("Built output {} rows={} columns={}", target_name, len(final), len(final.columns))
        return final

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=supervisor_portal layer=data_process")
        store = self._build_store()
        store_sales = self._build_store_sales()
        outputs = {
            "supervisor_portal_store": store,
            "supervisor_portal_store_sales": store_sales,
            "supervisor_portal_salesman": self._aggregate_common(
                store,
                ["store_manager_code", "store_manager_name"],
                "supervisor_portal_salesman",
            ),
            "supervisor_portal_salesman_sales": self._aggregate_sales(
                store_sales,
                ["store_manager_code", "store_manager_name", "rtm_channel_name", "segment", "subsegment"],
                "supervisor_portal_salesman_sales",
            ),
            "supervisor_portal_mars_geo": self._aggregate_common(
                store,
                ["mars_region_code", "mars_province_code", "mars_city_cluster_code", "mars_city_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name"],
                "supervisor_portal_mars_geo",
            ),
            "supervisor_portal_mars_geo_sales": self._aggregate_sales(
                store_sales,
                ["mars_region_code", "mars_province_code", "mars_city_cluster_code", "mars_city_code", "mars_region_name", "mars_province_name", "mars_city_cluster_name", "mars_city_name", "rtm_channel_name", "segment", "subsegment"],
                "supervisor_portal_mars_geo_sales",
            ),
            "user_information": self._user_information(),
        }
        return outputs
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")

def write_supervisor_portal_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import threading
from typing import Dict, List, Optional, Tuple

from common_utils.all_modules import logger, pd
from gateway.client import GateWayClient
from params_configs.col_config import (
    hbase_export_cols,
    hbase_export_range,
    mssql_columns_rename,
    mssql_export_cols,
    mssql_export_range,
)
from params_configs.db_config import app_key, app_secret, fs_root_dir, mssql_token, mssql_url


class DataSource:
    """Read supervisor-portal sources for the resolved reporting range."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        current_date = str(self.params.get("current_date") or datetime.datetime.now().strftime("%Y-%m-%d"))[:10]
        current_dt = pd.to_datetime(current_date)
        currentday = current_dt.strftime("%Y%m%d")
        yesterday_dt = current_dt - pd.Timedelta(days=1)
        period = str(self.params.get("period") or self.params.get("P") or "")
        p_start = str(self.params.get("p_start") or self.params.get("p_start_date") or "")
        p_end = str(self.params.get("p_end") or self.params.get("p_end_date") or "")
        time_range = {
            "current_date": current_dt.strftime("%Y-%m-%d"),
            "currentday": currentday,
            "yesterday": yesterday_dt.strftime("%Y%m%d"),
            "yester_day": yesterday_dt.strftime("%Y-%m-%d"),
            "period": period,
            "P": period,
            "p_start": p_start or period,
            "p_end": p_end or period,
            "p_start_time": str(self.params.get("p_start_time") or (pd.to_datetime(p_start).strftime("%Y-%m-%d") if p_start else current_dt.strftime("%Y-%m-%d"))),
            "p_end_time": str(self.params.get("p_end_time") or current_dt.strftime("%Y-%m-%d")),
            "r2p": str(self.params.get("r2p") or p_start or currentday),
        }
        logger.info(
            "time_range_resolved component=supervisor_portal period={} current_date={} start={} end={}",
            time_range.get("period"),
            time_range.get("current_date"),
            time_range.get("p_start_time"),
            time_range.get("p_end_time"),
        )
        return time_range

    def _gateway_client(self):
        if self.params.get("gateway_client") is not None:
            return self.params["gateway_client"]
        return GateWayClient(app_key, app_secret)

    def _hbase_client(self):
        if self.params.get("hbase_client") is not None:
            return self.params["hbase_client"]
        return self._gateway_client().getHbaseClient(fs_root_dir)

    def read_hbase_2_df(
        self,
        table_name: str,
        columns: List[str],
        row_start: Optional[str] = None,
        row_stop: Optional[str] = None,
        row_prefixs: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        injected = self.params.get("hbase_data", {})
        if table_name in injected:
            df = injected[table_name].copy()
        else:
            df = self._hbase_client().query_df(
                hbase_table_name=table_name,
                columns=columns,
                row_start=row_start,
                row_stop=row_stop,
                row_prefixs=row_prefixs,
            )
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns] if columns else df

    def _range_value(self, time_range: dict, key):
        if key is None:
            return None
        return time_range.get(str(key), str(key))

    def _read_hbase_with_range(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        row_start = self._range_value(time_range, fetch_range.get("start_time"))
        row_stop = self._range_value(time_range, fetch_range.get("end_time"))
        row_prefixs = [str(index) for index in range(10)] if fetch_range.get("row_prefixs") else None
        if row_start is not None and row_stop is not None:
            row_stop = f"{row_stop}Z"
        logger.info(
            "source_read_start storage=hbase table={} selected_columns={} range_start={} range_end={} row_prefix_mode={}",
            table_name,
            len(columns),
            row_start,
            row_stop,
            bool(row_prefixs),
        )
        return self.read_hbase_2_df(table_name, columns, row_start=row_start, row_stop=row_stop, row_prefixs=row_prefixs)

    def fetch_hbase_tables(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {}
        threads = []

        def worker(table_name: str):
            df_map[table_name] = self._read_hbase_with_range(
                table_name,
                hbase_export_cols.get(table_name, []),
                hbase_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("HBase table={} rows={}", table_name, len(df_map[table_name]))

        for table_name in hbase_export_cols:
            thread = threading.Thread(target=worker, args=(table_name,))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        return df_map

    def _mssql_client(self):
        if self.params.get("mssql_client") is not None:
            return self.params["mssql_client"]
        raise RuntimeError(
            "No mssql_client supplied. Fill mssql_url/mssql_token and adapt _mssql_client for the deployment runtime."
        )

    def _mssql_sql(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> str:
        select_cols = ", ".join(columns) if columns else "*"
        time_col = fetch_range.get("time_col")
        if time_col:
            start_time = pd.to_datetime(time_range[fetch_range["start_time"]]).strftime("%Y-%m-%d %H:%M:%S")
            end_time = pd.to_datetime(time_range[fetch_range["end_time"]]).replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            return f"SELECT {select_cols} FROM {table_name} WHERE {time_col} BETWEEN '{start_time}' AND '{end_time}'"
        r2p = time_range.get("r2p", "")
        return (
            f"SELECT {select_cols} FROM {table_name} "
            "WHERE (cover_mode LIKE '%糖巧固定覆盖%' OR cover_mode LIKE '%糖巧非固定覆盖%' OR cover_mode LIKE '%糖巧线路外覆盖%') "
            f"AND (state = 1 OR (state = 0 AND closed_date > '{r2p}'))"
        )

    def read_mssql_2_df(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        injected = self.params.get("mssql_data", {})
        if table_name in injected:
            df = injected[table_name].copy()
        else:
            client = self._mssql_client()
            sql = self._mssql_sql(table_name, columns, fetch_range, time_range)
            logger.info(
                "source_query storage=mssql table={} selected_columns={} predicate={}",
                table_name,
                len(columns),
                "time_range" if fetch_range.get("time_col") else "coverage_and_state",
            )
            if hasattr(client, "read_sql"):
                df = client.read_sql(sql)
            elif hasattr(client, "query_df"):
                df = client.query_df(sql)
            else:
                raise RuntimeError("mssql_client must provide read_sql(sql) or query_df(sql).")
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in df.columns:
                df[column] = None
        if table_name in mssql_columns_rename:
            df = df.rename(columns=mssql_columns_rename[table_name])
        return df

    def fetch_mssql_tables(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {}
        threads = []

        def worker(table_name: str):
            df_map[table_name] = self.read_mssql_2_df(
                table_name,
                mssql_export_cols.get(table_name, []),
                mssql_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("MSSQL table={} rows={}", table_name, len(df_map[table_name]))

        for table_name in mssql_export_cols:
            thread = threading.Thread(target=worker, args=(table_name,))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        return df_map

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=supervisor_portal layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        source_data.update(self.fetch_hbase_tables(time_range))
        source_data.update(self.fetch_mssql_tables(time_range))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")

def write_supervisor_portal_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import hashlib
import time

from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map, target_table_columns


class DataStorage:
    """Replace supervisor-portal ClickHouse outputs using confirmed predicates."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params
        self.current_date = str(time_range.get("current_date") or "")

    def _get_clickhouse_client(self):
        injected_client = self.params.get("clickhouse_client")
        if injected_client is None:
            raise RuntimeError("No clickhouse_client supplied. Fill deployment ClickHouse client before running writes.")
        return injected_client

    def _generate_batch_id(self) -> str:
        return hashlib.md5(str(time.time()).encode("utf-8")).hexdigest()

    def _command(self, client, sql: str):
        operation = sql.strip().split(maxsplit=1)[0].upper() if sql.strip() else "UNKNOWN"
        logger.info("target_command storage=clickhouse operation={} statement_length={}", operation, len(sql))
        if hasattr(client, "command"):
            return client.command(sql)
        if hasattr(client, "execute"):
            return client.execute(sql)
        raise RuntimeError("clickhouse_client must provide command(sql) or execute(sql).")

    def _query_df(self, client, sql: str) -> pd.DataFrame:
        if hasattr(client, "query_df"):
            return client.query_df(sql)
        if hasattr(client, "query_dataframe"):
            return client.query_dataframe(sql)
        return pd.DataFrame()

    def _insert_dataframe(self, client, table_name: str, df: pd.DataFrame):
        if hasattr(client, "insert_df"):
            return client.insert_df(table_name, df)
        if hasattr(client, "insert_dataframe"):
            return client.insert_dataframe(table_name, df)
        raise RuntimeError("clickhouse_client must provide insert_df(table, df) or insert_dataframe(table, df).")

    def _next_batch_row_id(self, client) -> int:
        df_max = self._query_df(client, "select max(id) as id from supervisor_portal.supervisor_portal_batch")
        if df_max.empty or pd.isna(df_max.iloc[0].get("id")):
            return 1
        return int(df_max.iloc[0]["id"]) + 1

    def _insert_batch_status(self, client, row_id: int, table_name: str, batch_id: str, status: str, timestamp: str):
        sql = (
            "INSERT INTO supervisor_portal.supervisor_portal_batch "
            "(id, table_name, batch_id, status, last_update_time) "
            f"VALUES({row_id}, '{table_name}', '{batch_id}', '{status}', '{timestamp}')"
        )
        self._command(client, sql)

    def _update_batch_status(self, client, table_name: str, batch_id: str, status: str, timestamp: str):
        sql = (
            "ALTER TABLE supervisor_portal.supervisor_portal_batch "
            f"UPDATE status = '{status}', last_update_time = '{timestamp}' "
            f"WHERE batch_id = '{batch_id}' and table_name = '{table_name}'"
        )
        self._command(client, sql)

    def _previous_batch(self, client, table_name: str, status: str):
        sql = (
            "select batch_id from supervisor_portal.supervisor_portal_batch "
            f"where status = '{status}' and table_name = '{table_name}' order by id desc limit 1"
        )
        df_batch = self._query_df(client, sql)
        if df_batch.empty:
            return None
        return df_batch.iloc[0].get("batch_id")

    def _upload_one(self, client, target_name: str, df: pd.DataFrame):
        physical_table = target_table_map.get(target_name, target_name)
        clickhouse_table = physical_table.split(".")[-1]
        final_columns = target_table_columns.get(target_name, [])
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} reason=empty_output", target_name)
            return {"target": physical_table, "rows": 0, "status": "skipped_empty"}
        df = df.copy()
        batch_id = self._generate_batch_id()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for column in final_columns:
            if column not in df.columns:
                df[column] = None
        if "batch_id" in final_columns:
            df["batch_id"] = batch_id
        if "last_update_time" in final_columns:
            df["last_update_time"] = timestamp
        if "date" in final_columns:
            df["date"] = self.current_date
        if final_columns:
            df = df.reindex(columns=final_columns)

        row_id = self._next_batch_row_id(client)
        old_finished_batch = self._previous_batch(client, clickhouse_table, "2")
        old_cancelled_batch = self._previous_batch(client, clickhouse_table, "3")
        self._insert_batch_status(client, row_id, clickhouse_table, batch_id, "1", timestamp)
        logger.info("Inserting ClickHouse table={} rows={}", physical_table, len(df))
        self._insert_dataframe(client, physical_table, df)
        finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._update_batch_status(client, clickhouse_table, batch_id, "2", finish_time)
        if old_finished_batch:
            self._update_batch_status(client, clickhouse_table, old_finished_batch, "3", finish_time)
        if old_cancelled_batch:
            delete_sql = f"DELETE FROM supervisor_portal.{clickhouse_table} where batch_id = '{old_cancelled_batch}'"
            self._command(client, delete_sql)
        return {"target": physical_table, "rows": len(df), "status": "inserted", "batch_id": batch_id}

    def run(self):
        logger.info("component_start component=supervisor_portal layer=data_storage")
        client = self._get_clickhouse_client()
        metrics = []
        for target_name, df in self.outputs.items():
            metrics.append(self._upload_one(client, target_name, df))
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")
