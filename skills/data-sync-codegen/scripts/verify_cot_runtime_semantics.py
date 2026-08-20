#!/usr/bin/env python3
"""Verify generated COT sync runtime semantics without connecting to services."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


MODULE_NAMES = [
    "loguru",
    "plugin_common",
    "sync_with_period",
    "sync_without_period",
    "plugin_main",
    "cot_config",
    "cot_config.plugin_config",
    "cot_sync_with_period",
    "cot_sync_with_period.ck_operation",
    "cot_sync_with_period.etl_source",
    "cot_sync_with_period.hbase_operation",
    "cot_sync_without_period",
    "cot_sync_without_period.ck_operation",
    "cot_sync_without_period.etl_source",
    "cot_sync_without_period.hbase_operation",
]


class NoopLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, *args: Any, **kwargs: Any) -> None:
        return None

    def exception(self, *args: Any, **kwargs: Any) -> None:
        return None


def make_loguru() -> types.ModuleType:
    module = types.ModuleType("loguru")
    module.logger = NoopLogger()
    return module


def import_from_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def isolated_imports(project_dir: Path, overrides: Dict[str, types.ModuleType]):
    saved_modules = {name: sys.modules.get(name) for name in MODULE_NAMES}
    old_path = list(sys.path)
    try:
        for name in MODULE_NAMES:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(project_dir))
        sys.modules["loguru"] = make_loguru()
        for name, module in overrides.items():
            sys.modules[name] = module
        yield
    finally:
        for name in MODULE_NAMES:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module
        sys.path[:] = old_path


def assert_event_order(events: List[Tuple[Any, ...]], expected: Iterable[str]) -> None:
    names = [event[0] for event in events]
    cursor = 0
    for expected_name in expected:
        try:
            index = names.index(expected_name, cursor)
        except ValueError as exc:
            raise AssertionError(f"missing event {expected_name}; events={names}") from exc
        cursor = index + 1


def fake_common(events: List[Tuple[Any, ...]]) -> types.ModuleType:
    module = types.ModuleType("plugin_common")

    class TimeStamp_Update:
        def fetch_last_timestamp(self, mysql_table: str) -> str:
            events.append(("fetch_timestamp", mysql_table))
            return "2026-05-31 08:00:00"

        def update_last_timestamp(self, mysql_table: str, last_update_timestamp: str) -> None:
            events.append(("update_timestamp", mysql_table, str(last_update_timestamp)))

    def clean_local_directory(file_dir: str) -> None:
        events.append(("clean_dir", file_dir))

    def clean_local_files(file_dir: str) -> None:
        events.append(("clean_files", file_dir))

    def format_exception() -> str:
        return "fake formatted exception"

    def return_pipeline_result(metrics: list) -> dict:
        events.append(("return_result", len(metrics)))
        return {"metrics": metrics}

    module.TimeStamp_Update = TimeStamp_Update
    module.clean_local_directory = clean_local_directory
    module.clean_local_files = clean_local_files
    module.format_exception = format_exception
    module.return_pipeline_result = return_pipeline_result
    return module


def make_with_period_modules(events: List[Tuple[Any, ...]], sync_list: Any, last_update: Any):
    etl = types.ModuleType("cot_sync_with_period.etl_source")
    ck = types.ModuleType("cot_sync_with_period.ck_operation")
    hbase = types.ModuleType("cot_sync_with_period.hbase_operation")

    def get_mysql_url(mysql_table: str):
        events.append(("get_mysql_url", mysql_table))
        return "mysql://placeholder", {"db": "report_ps_p"}

    def create_mysql_engine(mysql_url: str):
        events.append(("create_mysql_engine", mysql_url))
        return "engine"

    def get_sync_mode(mysql_table, last_update_time_column, period_column, last_timestamp, period, engine, mysql_params):
        events.append(("get_sync_mode", mysql_table, last_timestamp, period))
        return sync_list, last_update

    def fetch_mysql(mysql_table, last_update_time_column, period_column, last_timestamp, sync_items, file_dir, batch_size, engine, mysql_params):
        events.append(("fetch_mysql", mysql_table, last_timestamp, tuple(sync_items)))
        return {"operation": "fetch_mysql_data", "mysql_size": 2}

    def clickhouse_op(file_dir, sync_items, clickhouse_table, period_column, code_column, mysql_table):
        events.append(("write_clickhouse", clickhouse_table, tuple(sync_items), period_column, code_column))
        return {"operation": "insert_clickhouse", "clickhouse_size": 2}

    def hbase_op(hbase_table, file_dir, sync_items, rowkey_rule_columns):
        events.append(("write_hbase", hbase_table, tuple(sync_items), tuple(rowkey_rule_columns)))
        return {"operation": "insert_hbase", "hbase_size": 2}

    etl.get_mysql_url = get_mysql_url
    etl.create_mysql_engine = create_mysql_engine
    etl.get_sync_mode = get_sync_mode
    etl.fetch_mysql = fetch_mysql
    ck.clickhouse_op = clickhouse_op
    hbase.hbase_op = hbase_op
    return {
        "cot_sync_with_period.etl_source": etl,
        "cot_sync_with_period.ck_operation": ck,
        "cot_sync_with_period.hbase_operation": hbase,
    }


def make_without_period_modules(events: List[Tuple[Any, ...]], is_sync: bool, last_update: Any, sync_size: int):
    etl = types.ModuleType("cot_sync_without_period.etl_source")
    ck = types.ModuleType("cot_sync_without_period.ck_operation")
    hbase = types.ModuleType("cot_sync_without_period.hbase_operation")

    class ETLSource:
        def __init__(self, mysql_table: str):
            events.append(("etl_init", mysql_table))

        def fetch_sync_mode(self, mysql_table, last_update_time_column, last_timestamp):
            events.append(("detect_changes", mysql_table, last_timestamp))
            return is_sync, last_update, sync_size

        def fetch_mysql(self, mysql_table, last_update_time_column, last_timestamp, file_dir, batch_size):
            events.append(("fetch_mysql", mysql_table, last_timestamp))
            return {"operation": "fetch_mysql_data", "mysql_size": sync_size}

    class CLickHouseOperation:
        def __init__(self):
            events.append(("ck_init",))

        def clickhouse_op(self, file_dir, clickhouse_table, last_update_time_column, last_timestamp, key_column):
            events.append(("write_clickhouse", clickhouse_table, last_timestamp, key_column))
            return {"operation": "insert_clickhouse", "clickhouse_size": sync_size}

    class HBaseOperation:
        def __init__(self):
            events.append(("hbase_init",))

        def hbase_op(self, hbase_table, file_dir, rowkey_rule_columns):
            events.append(("write_hbase", hbase_table, tuple(rowkey_rule_columns)))
            return {"operation": "insert_hbase", "hbase_size": sync_size}

    etl.ETLSource = ETLSource
    ck.CLickHouseOperation = CLickHouseOperation
    hbase.HBaseOperation = HBaseOperation
    return {
        "cot_sync_without_period.etl_source": etl,
        "cot_sync_without_period.ck_operation": ck,
        "cot_sync_without_period.hbase_operation": hbase,
    }


def with_period_params(period: Any = None) -> Dict[str, Any]:
    source = {
        "mysql_table": "zo_hswmt_detail_p",
        "last_update_time_column": "inksaa_last_modified_timestamp",
        "period_column": "period",
        "code_column": "code",
        "batch_size": 100000,
        "receiver_emails": [],
    }
    if period is not None:
        source["period"] = period
    return {
        "source_informations": source,
        "hbase_informations": {
            "hbase_table": "l2_cot_perfect_store.zo_hswmt_detail_2026_p",
            "rowkey_rule_columns": ["period", "code"],
        },
        "clickhouse_information": {"clickhouse_table": "zo_hswmt_detail_p"},
    }


def without_period_params() -> Dict[str, Any]:
    return {
        "source_informations": {
            "mysql_table": "rpt_exe_visit_frequency_by_people",
            "last_update_time_column": "inksaa_last_modified_timestamp",
            "key_column": "id",
            "batch_size": 100000,
            "receiver_emails": [],
        },
        "hbase_informations": {
            "hbase_table": "l2_cot_exe_report.rpt_exe_visit_frequency_by_people",
            "rowkey_rule_columns": ["id"],
        },
        "clickhouse_information": {"clickhouse_table": "rpt_exe_visit_frequency_by_people"},
    }


def test_with_period_manual(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []
    overrides = {"plugin_common": fake_common(events)}
    overrides.update(make_with_period_modules(events, [("SHOULD_NOT_USE", "delta")], "2026-06-01 00:00:00"))
    with isolated_imports(project_dir, overrides):
        module = import_from_path("sync_with_period", project_dir / "sync_with_period.py")
        result = module.COT_REPORT_WITH_P(with_period_params(period=["2026P03"])).run()
    assert "fetch_timestamp" not in [event[0] for event in events], events
    assert "get_sync_mode" not in [event[0] for event in events], events
    assert "update_timestamp" not in [event[0] for event in events], events
    assert_event_order(events, ["clean_dir", "fetch_mysql", "write_clickhouse", "write_hbase", "return_result", "clean_files"])
    fetch_event = next(event for event in events if event[0] == "fetch_mysql")
    assert fetch_event[2] is None, events
    assert fetch_event[3] == (("2026P03", "full"),), events
    return {"case": "with_period_manual", "events": events, "result_metric_count": len(result["metrics"])}


def test_with_period_incremental(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []
    overrides = {"plugin_common": fake_common(events)}
    overrides.update(make_with_period_modules(events, [("2026P03", "delta")], "2026-06-01 09:00:00"))
    with isolated_imports(project_dir, overrides):
        module = import_from_path("sync_with_period", project_dir / "sync_with_period.py")
        result = module.COT_REPORT_WITH_P(with_period_params()).run()
    assert_event_order(
        events,
        ["clean_dir", "fetch_timestamp", "get_sync_mode", "fetch_mysql", "write_clickhouse", "write_hbase", "update_timestamp", "return_result", "clean_files"],
    )
    update_event = next(event for event in events if event[0] == "update_timestamp")
    assert update_event[2] == "2026-06-01 09:00:00", events
    return {"case": "with_period_incremental", "events": events, "result_metric_count": len(result["metrics"])}


def test_with_period_no_changes(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []
    overrides = {"plugin_common": fake_common(events)}
    overrides.update(make_with_period_modules(events, None, None))
    with isolated_imports(project_dir, overrides):
        module = import_from_path("sync_with_period", project_dir / "sync_with_period.py")
        result = module.COT_REPORT_WITH_P(with_period_params()).run()
    names = [event[0] for event in events]
    assert "fetch_mysql" not in names and "write_clickhouse" not in names and "write_hbase" not in names, events
    assert "update_timestamp" not in names, events
    assert result["metrics"][0]["status"] == "no_changed_periods", result
    return {"case": "with_period_no_changes", "events": events, "result_metric_count": len(result["metrics"])}


def test_without_period_changed(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []
    overrides = {"plugin_common": fake_common(events)}
    overrides.update(make_without_period_modules(events, True, "2026-06-01 10:00:00", 3))
    with isolated_imports(project_dir, overrides):
        module = import_from_path("sync_without_period", project_dir / "sync_without_period.py")
        result = module.COT_REPORT_WITHOUT_P(without_period_params()).run()
    assert_event_order(
        events,
        ["etl_init", "clean_dir", "fetch_timestamp", "detect_changes", "fetch_mysql", "write_clickhouse", "write_hbase", "update_timestamp", "return_result", "clean_files"],
    )
    update_event = next(event for event in events if event[0] == "update_timestamp")
    assert update_event[2] == "2026-06-01 10:00:00", events
    return {"case": "without_period_changed", "events": events, "result_metric_count": len(result["metrics"])}


def test_without_period_no_changes(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []
    overrides = {"plugin_common": fake_common(events)}
    overrides.update(make_without_period_modules(events, False, None, 0))
    with isolated_imports(project_dir, overrides):
        module = import_from_path("sync_without_period", project_dir / "sync_without_period.py")
        result = module.COT_REPORT_WITHOUT_P(without_period_params()).run()
    names = [event[0] for event in events]
    assert "fetch_mysql" not in names and "write_clickhouse" not in names and "write_hbase" not in names, events
    assert "update_timestamp" not in names, events
    assert result["metrics"][0]["status"] == "no_changed_rows", result
    return {"case": "without_period_no_changes", "events": events, "result_metric_count": len(result["metrics"])}


def test_plugin_main_defaults(project_dir: Path) -> Dict[str, Any]:
    events: List[Tuple[Any, ...]] = []

    sync_with = types.ModuleType("sync_with_period")
    sync_without = types.ModuleType("sync_without_period")

    class COT_REPORT_WITH_P:
        def __init__(self, params: dict):
            events.append(("with_init", params))
            self.params = params

        def run(self):
            events.append(("with_run", self.params["source_informations"]["mysql_table"]))
            return {"branch": "with", "params": self.params}

    class COT_REPORT_WITHOUT_P:
        def __init__(self, params: dict):
            events.append(("without_init", params))
            self.params = params

        def run(self):
            events.append(("without_run", self.params["source_informations"]["mysql_table"]))
            return {"branch": "without", "params": self.params}

    sync_with.COT_REPORT_WITH_P = COT_REPORT_WITH_P
    sync_without.COT_REPORT_WITHOUT_P = COT_REPORT_WITHOUT_P
    with isolated_imports(project_dir, {"sync_with_period": sync_with, "sync_without_period": sync_without}):
        module = import_from_path("plugin_main", project_dir / "plugin_main.py")
        with_result = module.calc_single({"source_informations": {"mysql_table": "ic_detail_gb_p"}})
        without_result = module.calc_single({"source_informations": {"mysql_table": "rpt_exe_visit_frequency_by_people"}})

    assert with_result["branch"] == "with", with_result
    assert without_result["branch"] == "without", without_result
    with_params = with_result["params"]
    without_params = without_result["params"]
    assert with_params["hbase_informations"]["hbase_table"] == "l2_cot_perfect_store.ic_detail_gb_2026_p", with_params
    assert with_params["clickhouse_information"]["clickhouse_table"] == "ic_detail_gb_p", with_params
    assert with_params["source_informations"]["period_column"] == "period", with_params
    assert without_params["hbase_informations"]["rowkey_rule_columns"] == ["id"], without_params
    assert without_params["clickhouse_information"]["clickhouse_table"] == "rpt_exe_visit_frequency_by_people", without_params
    return {"case": "plugin_main_defaults", "events": events, "with_table": with_params["source_informations"]["mysql_table"]}


def run_verification(project_dir: Path) -> Dict[str, Any]:
    cases = [
        test_plugin_main_defaults,
        test_with_period_manual,
        test_with_period_incremental,
        test_with_period_no_changes,
        test_without_period_changed,
        test_without_period_no_changes,
    ]
    results = []
    for case in cases:
        results.append(case(project_dir))
    return {"status": "ok", "case_count": len(results), "cases": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="Generated COT sync project directory.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_verification(args.project_dir.resolve())
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
