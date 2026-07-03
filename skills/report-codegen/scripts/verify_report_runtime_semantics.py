#!/usr/bin/env python3
"""Verify generated report project runtime semantics with fake data."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List


PROJECT_MODULE_PREFIXES = [
    "common_utils",
    "data_utils",
    "params_configs",
    "gateway",
    "hbase",
    "fs",
    "main_execute",
    "plugin_main",
]


@contextmanager
def project_import_context(project_dir: Path):
    old_path = list(sys.path)
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if any(name == prefix or name.startswith(prefix + ".") for prefix in PROJECT_MODULE_PREFIXES)
    }
    try:
        for name in list(saved):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(project_dir))
        yield
    finally:
        for name in list(sys.modules):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in PROJECT_MODULE_PREFIXES):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
        sys.path[:] = old_path


def import_from_project(module_name: str, project_dir: Path):
    module_path = project_dir / (module_name.replace(".", "/") + ".py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str, details: Any = None) -> None:
    if not condition:
        raise AssertionError(f"{message}: {details!r}")


def fake_supervisor_source_data(pd):
    current = "2026-06-01"
    return {
        "params": {
            "current_date": current,
            "period": "2026P06",
            "p_start": "2026-05-30",
            "p_end": "2026-06-01",
            "hbase_data": {
                "l0_eo.order_details_sync": pd.DataFrame(
                    [
                        {
                            "customers_code": "S001",
                            "order_date": "2026-05-31 10:00:00",
                            "order_status": "已完成",
                            "order_pt_sum": 40,
                            "product_std_code": "P1",
                        },
                        {
                            "customers_code": "S001",
                            "order_date": "2026-05-31 11:00:00",
                            "order_status": "已取消",
                            "order_pt_sum": 999,
                            "product_std_code": "P1",
                        },
                    ]
                ),
                "l2_cot_exe_report.rpt_exe_visit_planning_execute_rate": pd.DataFrame(
                    [
                        {
                            "store_code": "S001",
                            "today_executed": 1,
                            "planning_date": "2026-05-31",
                            "visit_emp_segment": "MW",
                        },
                        {
                            "store_code": "S001",
                            "today_executed": 1,
                            "planning_date": "2026-05-31",
                            "visit_emp_segment": "OTHER",
                        },
                    ]
                ),
                "l0_cot_visit.store_planning": pd.DataFrame(
                    [
                        {"store_code": "S001", "planning_date": current, "user_segment": "MW"},
                        {"store_code": "S002", "planning_date": current, "user_segment": "OTHER"},
                    ]
                ),
                "l0_user_center.user_information": pd.DataFrame(
                    [
                        {
                            "emp_code": "E001",
                            "emp_name": "Alice",
                            "level_code": "L1",
                            "emp_type_name": "Sales",
                            "parent_emp_code": "M001",
                            "parent_emp_name": "Manager",
                            "ad_account": "alice",
                            "mars_geo_code1": "R1",
                            "mars_geo_name1": "East",
                            "mars_geo_code2": "P1",
                            "mars_geo_name2": "Province",
                            "mars_geo_code3": "C1",
                            "mars_geo_name3": "Cluster",
                            "mars_geo_code4": "CITY1",
                            "mars_geo_name4": "City",
                            "status": "1",
                            "org_code_ hierachy": "ORG",
                            "org_name_ hierachy": "Org",
                            "roles_code": "ROLE",
                            "roles_name": "Role",
                            "is_cheetah": "0",
                            "is_vehicle": "0",
                            "is_wholesale": "0",
                            "is_lst": "0",
                            "user_channel": "MW",
                            "created": "2026-01-01",
                            "updated": "2026-06-01",
                            "id": 1,
                            "segment": "MW",
                        }
                    ]
                ),
                "l0_product_center.locust_product_md": pd.DataFrame(
                    [{"prod_code": "P1", "segment": "Chocolate", "subsegment": "Bar"}]
                ),
            },
            "mssql_data": {
                "topic_supervisor_portal.store_details": pd.DataFrame(
                    [
                        {
                            "mars_region_code": "R1",
                            "mars_province_code": "P1",
                            "mars_city_cluster_code": "CC1",
                            "mars_city_code": "C1",
                            "region_code": "RG1",
                            "chain_brand_code": "CB1",
                            "nation_hq_code": "NH1",
                            "city_hq_code": "CH1",
                            "ka_type_code": "KA1",
                            "channel_code": "TT",
                            "channel_level2_code": "L2",
                            "store_channel_code": "SC1",
                            "rtm_channel_code": "FT-TT",
                            "mars_region_name": "East",
                            "mars_province_name": "Province",
                            "mars_city_cluster_name": "Cluster",
                            "mars_city_name": "City",
                            "region_name": "Region",
                            "chain_brand_name": "Chain",
                            "nation_hq_name": "Nation",
                            "ka_type_name": "KA",
                            "city_hq_name": "CityHQ",
                            "code": "S001",
                            "store_name": "Store One",
                            "cover_mode": "糖巧固定覆盖",
                            "channel_name": "Channel",
                            "channel_level2_name": "Channel2",
                            "store_channel_name": "StoreChannel",
                            "store_level": "A",
                            "wal_mart": "N",
                            "salesman_code": "SA001",
                            "salesman_name": "Sales A",
                            "state": "1",
                            "digital": "现售",
                            "rtm_channel_name": "FT-TT",
                            "store_kk": "KK",
                            "store_manager_code": "SM001",
                            "store_manager_name": "Store Manager",
                            "closed_date": "2099-12-31",
                        },
                        {
                            "mars_region_code": "R2",
                            "mars_province_code": "P2",
                            "mars_city_cluster_code": "CC2",
                            "mars_city_code": "C2",
                            "region_code": "RG2",
                            "chain_brand_code": "CB2",
                            "nation_hq_code": "NH2",
                            "city_hq_code": "CH2",
                            "ka_type_code": "KA2",
                            "channel_code": "TT",
                            "channel_level2_code": "L2",
                            "store_channel_code": "SC2",
                            "rtm_channel_code": "FT-TT",
                            "mars_region_name": "West",
                            "mars_province_name": "Province2",
                            "mars_city_cluster_name": "Cluster2",
                            "mars_city_name": "City2",
                            "region_name": "Region2",
                            "chain_brand_name": "Chain2",
                            "nation_hq_name": "Nation2",
                            "ka_type_name": "KA2",
                            "city_hq_name": "CityHQ2",
                            "code": "S002",
                            "store_name": "Store Two",
                            "cover_mode": "非目标覆盖",
                            "channel_name": "Channel",
                            "channel_level2_name": "Channel2",
                            "store_channel_name": "StoreChannel",
                            "store_level": "B",
                            "wal_mart": "N",
                            "salesman_code": "SA002",
                            "salesman_name": "Sales B",
                            "state": "1",
                            "digital": "现售",
                            "rtm_channel_name": "FT-TT",
                            "store_kk": "KK",
                            "store_manager_code": "SM002",
                            "store_manager_name": "Store Manager2",
                            "closed_date": "2099-12-31",
                        },
                    ]
                ),
                "topic_supervisor_portal.eo_order_detail_pool": pd.DataFrame(
                    [
                        {
                            "store_code": "S001",
                            "create_time": "2026-06-01 12:00:00",
                            "order_state": "已完成",
                            "pt_sum": 100,
                            "product_code": "P1",
                        },
                        {
                            "store_code": "S001",
                            "create_time": "2026-06-01 13:00:00",
                            "order_state": "4509",
                            "pt_sum": 999,
                            "product_code": "P1",
                        },
                    ]
                ),
                "topic_supervisor_portal.fts_store_visit_log": pd.DataFrame(
                    [
                        {"store_id": "S001", "created_timestamp": "2026-06-01 09:00:00", "status": "2"},
                        {"store_id": "S001", "created_timestamp": "2026-05-31 09:00:00", "status": "2"},
                    ]
                ),
            },
            "previous_store": pd.DataFrame(
                [
                    {
                        "store_code": "S001",
                        "today_sales": 30,
                        "today_is_visit_planned": 1,
                        "today_is_visited": 0,
                        "today_order_placed": 1,
                    }
                ]
            ),
            "previous_store_sales": pd.DataFrame(
                [
                    {
                        "store_code": "S001",
                        "segment": "Chocolate",
                        "subsegment": "Bar",
                        "today_sales": 30,
                        "pty_sales": 40,
                    }
                ]
            ),
        }
    }


def fake_vehicle_source_data(pd):
    return {
        "params": {
            "period": "2026P05",
            "hbase_data": {
                "l0_mdp.mars_calendar": pd.DataFrame(
                    [
                        {"dataid": "20260501", "m_year": "2026", "m_period": "05"},
                        {"dataid": "20260531", "m_year": "2026", "m_period": "05"},
                    ]
                ),
                "l0_dtr_order.t5_eo_erp_sales_order_line_p": pd.DataFrame(
                    [
                        {
                            "mars_order_header_no": "EO1",
                            "order_created_at": "2026-05-03 08:00:00",
                            "first_complete_time": "2026-05-04 07:00:00",
                            "order_status": "4516",
                            "order_source": "EO订单",
                            "sold_to_code": "CUST1",
                            "sold_to_name": "Customer One",
                            "mars_store_code": "S001",
                            "bmp_eo_order_category": "NDT",
                            "original_amount": 100,
                            "pt_sum": 100,
                            "coupon_amt": 10,
                            "mars_sku_no": "SKU_OK",
                            "bmp_mars_sku_no": "BSKU_OK",
                        },
                        {
                            "mars_order_header_no": "EO_CHIPS",
                            "order_created_at": "2026-05-04 08:00:00",
                            "first_complete_time": "2026-05-05 08:00:00",
                            "order_status": "4516",
                            "order_source": "EO订单",
                            "sold_to_code": "CUST1",
                            "sold_to_name": "Customer One",
                            "mars_store_code": "S001",
                            "bmp_eo_order_category": "NDT",
                            "original_amount": 999,
                            "pt_sum": 999,
                            "coupon_amt": 0,
                            "mars_sku_no": "SKU_CHIPS",
                            "bmp_mars_sku_no": "BSKU_CHIPS",
                        },
                        {
                            "mars_order_header_no": "ERP_DIFF",
                            "order_created_at": "2026-05-06 09:00:00",
                            "first_complete_time": "2026-05-09 10:00:00",
                            "order_status": "4508",
                            "order_source": "ERP订单",
                            "sold_to_code": "CUST2",
                            "sold_to_name": "Customer Two",
                            "mars_store_code": "S002",
                            "bmp_eo_order_category": "NDT",
                            "original_amount": 200,
                            "pt_sum": 100,
                            "coupon_amt": 0,
                            "mars_sku_no": "SKU_OK",
                            "bmp_mars_sku_no": "BSKU_OK",
                        },
                    ]
                ),
                "l0_store_center.store_details_p": pd.DataFrame(
                    [
                        {
                            "mars_region_name": "R1",
                            "mars_province_name": "P1",
                            "mars_city_cluster_name": "CC1",
                            "mars_city_name": "City1",
                            "region_name": "Region1",
                            "region_category": "Cat1",
                            "digital_district": "预售片区",
                            "code": "S001",
                            "store_name": "Store One",
                            "channel_name": "传统渠道",
                            "channel_level2_name": "L2",
                            "store_channel_name": "SC",
                            "rtm_channel_name": "RTM",
                            "digital": "预售",
                            "store_manager_code": "M001",
                            "store_manager_name": "Manager One",
                        },
                        {
                            "mars_region_name": "R2",
                            "mars_province_name": "P2",
                            "mars_city_cluster_name": "CC2",
                            "mars_city_name": "City2",
                            "region_name": "Region2",
                            "region_category": "Cat2",
                            "digital_district": "现售片区",
                            "code": "S002",
                            "store_name": "Store Two",
                            "channel_name": "传统渠道",
                            "channel_level2_name": "L2",
                            "store_channel_name": "SC",
                            "rtm_channel_name": "RTM",
                            "digital": "现售",
                            "store_manager_code": "M002",
                            "store_manager_name": "Manager Two",
                        },
                        {
                            "mars_region_name": "R3",
                            "mars_province_name": "P3",
                            "mars_city_cluster_name": "CC3",
                            "mars_city_name": "City3",
                            "region_name": "Region3",
                            "region_category": "Cat3",
                            "digital_district": "预售片区",
                            "code": "S003",
                            "store_name": "Store Three",
                            "channel_name": "传统渠道",
                            "channel_level2_name": "L2",
                            "store_channel_name": "SC",
                            "rtm_channel_name": "RTM",
                            "digital": "现售",
                            "store_manager_code": "M003",
                            "store_manager_name": "Manager Three",
                        },
                    ]
                ),
                "l2_cot_exe_report.rpt_exe_sales_assess_channel": pd.DataFrame(
                    [
                        {
                            "salesman_code": "M001",
                            "salesman_type": "Type1",
                            "sale_role": "Role1",
                            "mars_region_name": "SR1",
                            "mars_province_name": "SP1",
                            "mars_city_cluster_name": "SCC1",
                            "mars_city_name": "SCity1",
                        },
                        {
                            "salesman_code": "M002",
                            "salesman_type": "Type2",
                            "sale_role": "Role2",
                            "mars_region_name": "SR2",
                            "mars_province_name": "SP2",
                            "mars_city_cluster_name": "SCC2",
                            "mars_city_name": "SCity2",
                        },
                    ]
                ),
                "l1_mdp.vehicle_info_p": pd.DataFrame(
                    [
                        {
                            "CustomerNo": "CUST2",
                            "PlateNo": "",
                            "PersonalNo": "M002",
                            "SalesmanNo": "",
                            "SalesmanNo2": "",
                            "VehicleStatus": "行驶",
                            "DataType": "经销商三轮车",
                            "ModifyDate": "",
                            "CreateDate": "2026-04-01",
                            "PINNo": "PIN002",
                        },
                        {
                            "CustomerNo": "CUST1",
                            "PlateNo": "PLATE1",
                            "PersonalNo": "M001",
                            "SalesmanNo": "",
                            "SalesmanNo2": "",
                            "VehicleStatus": "停驶",
                            "DataType": "销售四轮车",
                            "ModifyDate": "2026-05-01",
                            "CreateDate": "2026-04-01",
                            "PINNo": "PIN001",
                        },
                    ]
                ),
                "l0_customer_center.locust_customer_md": pd.DataFrame(
                    [
                        {
                            "code": "CUST1",
                            "name": "Customer One",
                            "customer_type_code": "DT",
                            "division": "51",
                            "mars_geo_region_name": "CR1",
                            "mars_geo_province_name": "CP1",
                            "mars_geo_city_clusters_name": "CCC1",
                            "mars_geo_city_name": "CCity1",
                        },
                        {
                            "code": "CUST2",
                            "name": "Customer Two",
                            "customer_type_code": "DT",
                            "division": "51",
                            "mars_geo_region_name": "CR2",
                            "mars_geo_province_name": "CP2",
                            "mars_geo_city_clusters_name": "CCC2",
                            "mars_geo_city_name": "CCity2",
                        },
                    ]
                ),
                "l0_product_center.locust_product_md": pd.DataFrame(
                    [
                        {"prod_code": "SKU_OK", "subsegment": "Chocolate"},
                        {"prod_code": "BSKU_OK", "subsegment": "Chocolate"},
                        {"prod_code": "SKU_CHIPS", "subsegment": "Chips"},
                        {"prod_code": "BSKU_CHIPS", "subsegment": "Chips"},
                    ]
                ),
            },
            "fs_data": {
                "dms_order": pd.DataFrame(
                    [
                        {
                            "mars_store_code": "S001",
                            "org_mars_order_header_no": "DMS1",
                            "org_dtr_created_at": "2026-05-10 08:00:00",
                            "update_time": "2026-05-10 20:00:00",
                            "marsk": "0",
                            "reason_for_reversal": "",
                            "qct_total": 50,
                            "sales_amount": 50,
                            "org_coupon_amt": 5,
                            "supplier_code": "SUB1",
                            "supplier_name": "Sub One",
                            "org_dtr_source_type": "1",
                            "category": "Chocolate",
                        }
                    ]
                ),
                "dms_md": pd.DataFrame(
                    [
                        {
                            "code": "SUB1",
                            "status": "1",
                            "belongs_to_code": "CUST1",
                            "belongs_to_name": "Customer One",
                        }
                    ]
                ),
            },
        }
    }


class FakeClickHouseClient:
    def __init__(self, pd):
        self.pd = pd
        self.commands: List[str] = []
        self.inserts: List[Dict[str, Any]] = []
        self._max_id = 100

    def query_df(self, sql: str):
        self.commands.append(f"QUERY::{sql}")
        normalized = sql.lower()
        if "max(id)" in normalized:
            return self.pd.DataFrame([{"id": self._max_id}])
        if "status = '2'" in normalized:
            return self.pd.DataFrame([{"batch_id": "old_finished_batch"}])
        if "status = '3'" in normalized:
            return self.pd.DataFrame([{"batch_id": "old_cancelled_batch"}])
        return self.pd.DataFrame()

    def command(self, sql: str):
        self.commands.append(sql)

    def insert_df(self, table_name: str, df):
        self.inserts.append({"table": table_name, "rows": len(df), "columns": list(df.columns), "df": df.copy()})


def verify_supervisor_portal(project_dir: Path) -> Dict[str, Any]:
    with project_import_context(project_dir):
        all_modules = import_from_project("common_utils.all_modules", project_dir)
        pd = all_modules.pd
        source_module = import_from_project("data_utils.data_source", project_dir)
        process_module = import_from_project("data_utils.data_process", project_dir)
        storage_module = import_from_project("data_utils.data_storage", project_dir)
        col_config = import_from_project("params_configs.col_config", project_dir)

        data = fake_supervisor_source_data(pd)
        params = data["params"]
        source_data, time_range = source_module.DataSource(params).run()
        outputs = process_module.DataProcess(source_data, time_range, params).run()

        expected_outputs = {
            "supervisor_portal_store",
            "supervisor_portal_store_sales",
            "supervisor_portal_salesman",
            "supervisor_portal_salesman_sales",
            "supervisor_portal_mars_geo",
            "supervisor_portal_mars_geo_sales",
            "user_information",
        }
        require(set(outputs) == expected_outputs, "unexpected output table set", sorted(outputs))
        for name, df in outputs.items():
            expected_columns = col_config.target_table_columns[name]
            require(list(df.columns) == expected_columns, f"{name} column order mismatch", list(df.columns))

        store = outputs["supervisor_portal_store"]
        require(len(store) == 1, "store output should keep only sugar-covered active source store", store)
        row = store.iloc[0]
        require(row["store_code"] == "S001", "store_code mismatch", row.to_dict())
        require(float(row["today_sales"]) == 100.0, "today_sales mismatch", row.to_dict())
        require(float(row["yesterday_sales"]) == 30.0, "yesterday_sales mismatch", row.to_dict())
        require(float(row["pty_sales"]) == 40.0, "pty_sales mismatch", row.to_dict())
        require(float(row["ptd_sales"]) == 140.0, "ptd_sales mismatch", row.to_dict())
        require(int(row["today_is_visit_planned"]) == 1, "today plan flag mismatch", row.to_dict())
        require(int(row["today_is_visited"]) == 1, "today visit flag mismatch", row.to_dict())
        require(int(row["ptd_total_visits"]) == 2, "ptd_total_visits mismatch", row.to_dict())
        require(int(row["ptd_planned_visits_completed"]) == 2, "ptd planned completed mismatch", row.to_dict())
        require(int(row["ptd_total_planned_visits"]) == 2, "ptd total planned mismatch", row.to_dict())
        require(int(row["is_store_activated"]) == 1, "activation flag mismatch", row.to_dict())
        require(int(row["today_order_placed"]) == 1, "today order flag mismatch", row.to_dict())

        store_sales = outputs["supervisor_portal_store_sales"]
        require(len(store_sales) == 2, "store sales should include product dim plus empty dim", store_sales)
        chocolate = store_sales[
            (store_sales["store_code"] == "S001")
            & (store_sales["segment"] == "Chocolate")
            & (store_sales["subsegment"] == "Bar")
        ]
        require(len(chocolate) == 1, "missing Chocolate/Bar store-sales row", store_sales)
        require(float(chocolate.iloc[0]["today_sales"]) == 100.0, "store_sales today mismatch", chocolate.iloc[0].to_dict())
        require(float(chocolate.iloc[0]["yesterday_sales"]) == 30.0, "store_sales yesterday mismatch", chocolate.iloc[0].to_dict())
        require(float(chocolate.iloc[0]["pty_sales"]) == 40.0, "store_sales pty mismatch", chocolate.iloc[0].to_dict())
        require(float(chocolate.iloc[0]["ptd_sales"]) == 140.0, "store_sales ptd mismatch", chocolate.iloc[0].to_dict())

        salesman = outputs["supervisor_portal_salesman"]
        require(len(salesman) == 1, "salesman output row count mismatch", salesman)
        sm = salesman.iloc[0]
        require(float(sm["today_visit_plan_execution_rate"]) == 1.0, "today visit rate mismatch", sm.to_dict())
        require(int(sm["ptd_digital_visit_store_count"]) == 2, "ptd digital visit denominator mismatch", sm.to_dict())
        require(float(sm["ptd_store_activation_rate"]) == 0.5, "ptd activation rate mismatch", sm.to_dict())

        row_counts = {name: len(df) for name, df in outputs.items()}
        fake_client = FakeClickHouseClient(pd)
        params_with_client = {**params, "clickhouse_client": fake_client}
        storage_metrics = storage_module.DataStorage(outputs, time_range, params_with_client).run()
        require(len(storage_metrics) == 7, "storage metrics count mismatch", storage_metrics)
        require(len(fake_client.inserts) == 7, "ClickHouse insert count mismatch", fake_client.inserts)
        for insert in fake_client.inserts:
            columns = insert["columns"]
            table_tail = insert["table"].split(".")[-1]
            if table_tail != "user_information":
                require("batch_id" in columns and "last_update_time" in columns and "date" in columns, "missing batch columns", insert)
                inserted_df = insert["df"]
                require(inserted_df["batch_id"].notna().all(), "batch_id not filled", insert)
                require((inserted_df["date"] == "2026-06-01").all(), "date not filled", insert)
        command_text = "\n".join(fake_client.commands)
        require("INSERT INTO supervisor_portal.supervisor_portal_batch" in command_text, "missing batch insert command", command_text)
        require("UPDATE status = '2'" in command_text, "missing batch finish update", command_text)
        require("UPDATE status = '3'" in command_text, "missing old batch cancel update", command_text)
        require("DELETE FROM supervisor_portal." in command_text, "missing old cancelled batch delete", command_text)

        return {
            "status": "ok",
            "project_type": "supervisor_portal",
            "output_tables": sorted(outputs),
            "row_counts": row_counts,
            "insert_count": len(fake_client.inserts),
            "storage_metric_count": len(storage_metrics),
        }


def verify_vehicle_verification(project_dir: Path) -> Dict[str, Any]:
    with project_import_context(project_dir):
        all_modules = import_from_project("common_utils.all_modules", project_dir)
        pd = all_modules.pd
        source_module = import_from_project("data_utils.data_source", project_dir)
        process_module = import_from_project("data_utils.data_process", project_dir)
        storage_module = import_from_project("data_utils.data_storage", project_dir)
        col_config = import_from_project("params_configs.col_config", project_dir)

        data = fake_vehicle_source_data(pd)
        params = data["params"]
        source_data, time_range = source_module.DataSource(params).run()
        require(time_range["P"] == "2026P05", "vehicle P derivation mismatch", time_range)
        require(time_range["period"] == "202605", "vehicle compact period mismatch", time_range)

        outputs = process_module.DataProcess(source_data, time_range, params).run()
        expected_outputs = {
            "clickhouse_vehicle_verify_detail",
            "clickhouse_vehicle_verify_sum_ps_fs",
            "clickhouse_vehicle_verify_sum_fs",
        }
        require(set(outputs) == expected_outputs, "unexpected vehicle output set", sorted(outputs))
        for name, df in outputs.items():
            expected_columns = col_config.target_table_columns[name]
            require(list(df.columns) == expected_columns, f"{name} column order mismatch", list(df.columns))

        detail = outputs["clickhouse_vehicle_verify_detail"]
        require(len(detail) == 4, "vehicle detail should preserve valid orders plus no-order store", detail)
        require("EO_CHIPS" not in set(detail["order_code"].dropna().astype(str)), "chips/cereals order was not excluded", detail)

        eo_row = detail[detail["order_code"] == "EO1"].iloc[0]
        require(eo_row["period"] == "2026P05" and eo_row["year"] == "2026", "detail period/year mismatch", eo_row.to_dict())
        require(eo_row["is_difference_order"] == "否", "EO normal order diff flag mismatch", eo_row.to_dict())
        require(eo_row["is_48_deliver"] == "是", "EO 48h flag mismatch", eo_row.to_dict())
        require(eo_row["is_advance_order"] == "是", "EO advance flag mismatch", eo_row.to_dict())
        require(eo_row["customer_type"] == "经销商", "EO customer type mismatch", eo_row.to_dict())

        dms_row = detail[detail["order_code"] == "DMS1"].iloc[0]
        require(dms_row["order_source"] == "ERP订单", "DMS source mapping mismatch", dms_row.to_dict())
        require(dms_row["marsk"] == "新增单", "DMS marsk mapping mismatch", dms_row.to_dict())
        require(dms_row["customer_type"] == "二分商", "DMS customer type mismatch", dms_row.to_dict())
        require(dms_row["order_customer_code"] == "CUST1", "DMS belongs-to customer code mismatch", dms_row.to_dict())
        require(dms_row["order_customer_name"] == "Customer One", "DMS belongs-to customer name mismatch", dms_row.to_dict())

        diff_row = detail[detail["order_code"] == "ERP_DIFF"].iloc[0]
        require(diff_row["is_difference_order"] == "是", "difference order flag mismatch", diff_row.to_dict())
        require(float(diff_row["order_difference_amount"]) == 200.0, "difference amount mismatch", diff_row.to_dict())
        require(diff_row["is_48_deliver"] == "否", "difference order 48h flag mismatch", diff_row.to_dict())
        require(diff_row["vehicle_num"] == "PIN002", "three-wheel PIN fallback mismatch", diff_row.to_dict())
        require(diff_row["vehicle_status"] == "行驶", "vehicle status mismatch", diff_row.to_dict())

        no_order = detail[detail["code"] == "S003"].iloc[0]
        require(pd.isna(no_order["order_code"]), "no-order store should keep empty order_code", no_order.to_dict())
        require(no_order["order_source"] == "空", "no-order source default mismatch", no_order.to_dict())
        require(no_order["vehicle_tool"] == "公共交通或其他", "missing vehicle tool default mismatch", no_order.to_dict())
        require(no_order["vehicle_status"] == "空", "missing vehicle status default mismatch", no_order.to_dict())

        instock = outputs["clickhouse_vehicle_verify_sum_fs"]
        require(len(instock) == 1, "instock summary row count mismatch", instock)
        instock_row = instock.iloc[0]
        require(instock_row["vehicle_num"] == "PIN002", "instock vehicle number mismatch", instock_row.to_dict())
        require(instock_row["vehicle_customer_code"] == "CUST2", "instock vehicle customer code mismatch", instock_row.to_dict())
        require(instock_row["vehicle_customer_name"] == "Customer Two", "instock vehicle customer name mismatch", instock_row.to_dict())
        require(int(instock_row["store_count_sys"]) == 1, "instock store count mismatch", instock_row.to_dict())
        require(float(instock_row["total_amount"]) == 200.0, "instock total amount mismatch", instock_row.to_dict())
        require(float(instock_row["order_gsv"]) == 100.0, "instock order_gsv mismatch", instock_row.to_dict())
        require(float(instock_row["incentive_amount"]) == 2.0, "instock incentive mismatch", instock_row.to_dict())

        presale = outputs["clickhouse_vehicle_verify_sum_ps_fs"]
        require(len(presale) == 4, "presale summary row count mismatch", presale)
        presale_eo = presale[
            (presale["sold_to_code"] == "CUST1")
            & (presale["digital_district"] == "预售片区")
        ].iloc[0]
        require(float(presale_eo["48_delivery_rate"]) == 1.0, "presale EO 48 rate mismatch", presale_eo.to_dict())
        require(float(presale_eo["48_delivery_incentive_amount"]) == 2.0, "presale EO incentive mismatch", presale_eo.to_dict())
        presale_dms = presale[
            (presale["sold_to_code"] == "SUB1")
            & (presale["digital_district"] == "预售片区")
        ].iloc[0]
        require(presale_dms["order_customer_code"] == "CUST1", "presale DMS belongs-to mismatch", presale_dms.to_dict())
        require(float(presale_dms["order_gsv"]) == 50.0, "presale DMS GSV mismatch", presale_dms.to_dict())
        require(float(presale_dms["48_delivery_incentive_amount"]) == 1.0, "presale DMS incentive mismatch", presale_dms.to_dict())

        fake_client = FakeClickHouseClient(pd)
        metrics = storage_module.DataStorage(outputs, time_range, {**params, "clickhouse_client": fake_client}).run()
        require(len(metrics) == 3, "vehicle storage metrics count mismatch", metrics)
        require(len(fake_client.inserts) == 3, "vehicle insert count mismatch", fake_client.inserts)
        command_text = "\n".join(fake_client.commands)
        require("DELETE WHERE period = '2026P05'" in command_text, "vehicle delete-by-period mismatch", command_text)

        return {
            "status": "ok",
            "project_type": "vehicle_verification",
            "output_tables": sorted(outputs),
            "row_counts": {name: len(df) for name, df in outputs.items()},
            "insert_count": len(fake_client.inserts),
            "storage_metric_count": len(metrics),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="Generated report project directory.")
    parser.add_argument("--project-type", choices=["supervisor_portal", "vehicle_verification"], default="supervisor_portal")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.project_type == "supervisor_portal":
        result = verify_supervisor_portal(args.project_dir.resolve())
    elif args.project_type == "vehicle_verification":
        result = verify_vehicle_verification(args.project_dir.resolve())
    else:
        raise ValueError(f"unsupported project type: {args.project_type}")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
