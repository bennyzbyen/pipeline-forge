"""HBase prepare-pipeline scaffold writers."""

from __future__ import annotations

from pathlib import Path


def write_hbase_prepare_data_process(target: Path) -> None:
    content = '''# coding: utf-8
import time

from common_utils.all_modules import Dict, logger, pd
from params_configs.db_config import (
    pipeline_api_key,
    pipeline_base_url,
    pipeline_process_uids,
    pipeline_user_name,
)


try:
    import requests
except Exception:
    requests = None


class DataProcess:
    """Optionally activate downstream pipelines after HBase data is prepared."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def _run_one_pipeline(self, process_uid: str):
        injected = self.params.get("pipeline_client")
        if injected is not None:
            return injected.run(process_uid)
        if requests is None:
            raise RuntimeError("requests is unavailable; install it or inject pipeline_client for pipeline activation.")
        if not pipeline_base_url or pipeline_base_url.startswith("<"):
            raise RuntimeError("pipeline_base_url is a placeholder; fill deployment config before activation.")
        headers = {
            "Api-Key": pipeline_api_key,
            "X-Username": pipeline_user_name,
            "Content-Type": "application/json",
        }
        url = f"{pipeline_base_url}/build/projects/deliverables/processes/run"
        response = requests.post(url, params={"process_uid": process_uid}, headers=headers, verify=False)
        response.raise_for_status()
        result = response.json()
        if not result.get("successful"):
            raise RuntimeError(f"pipeline activation failed: {result}")
        return result

    def _activate_pipelines(self):
        process_uids = self.params.get("pipeline_process_uids") or pipeline_process_uids
        metrics = []
        for process_uid in process_uids:
            last_error = None
            for attempt in range(1, 7):
                try:
                    result = self._run_one_pipeline(str(process_uid))
                    metrics.append({"process_uid": str(process_uid), "status": "success", "result": result})
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "stage_retry stage=pipeline_activation uid={} attempt={} max_attempts=6 delay_seconds={} error_type={}",
                        process_uid,
                        attempt,
                        10 if attempt < 6 else 0,
                        type(exc).__name__,
                    )
                    if attempt < 6:
                        time.sleep(10)
            else:
                raise RuntimeError(f"pipeline activation failed for {process_uid}: {last_error}")
        return metrics

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=hbase_prepare layer=data_process")
        if self.params.get("is_run_pipeline", False):
            metrics = self._activate_pipelines()
            self.source_data["pipeline_metrics"] = pd.DataFrame(metrics)
        return self.source_data
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")

def write_hbase_prepare_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import os

from common_utils.all_modules import Dict, List, Tuple, datetime, logger, pd
from params_configs.col_config import (
    hbase_export_cols,
    hbase_prepare_default_export_cols,
    hbase_prepare_subsegment_filter,
    hbase_prepare_table,
)
from params_configs.db_config import app_key, app_secret, fs_root_dir, fs_save_source_dir


try:
    from gateway.client import GateWayClient
except Exception:
    GateWayClient = None


class DataSource:
    """Export confirmed HBase source rows to FS for downstream report components."""

    def __init__(self, params: dict):
        self.params = params
        self.current_date = params.get("current_date")
        self.fs_root_dir = params.get("fs_root_dir") or fs_root_dir
        self.fs_save_source_dir = params.get("fs_save_source_dir") or fs_save_source_dir

    def _gateway_client(self):
        injected = self.params.get("gateway_client")
        if injected is not None:
            return injected
        if GateWayClient is None:
            raise RuntimeError("gateway.client.GateWayClient is unavailable; install/copy fixed gateway package or inject clients.")
        return GateWayClient(app_key, app_secret)

    def _hbase_client(self):
        injected = self.params.get("hbase_client")
        if injected is not None:
            return injected
        return self._gateway_client().getHbaseClient(self.fs_root_dir)

    def _fs_client(self):
        injected = self.params.get("fs_client")
        if injected is not None:
            return injected
        return self._gateway_client().getFsClient()

    def _read_hbase_df(self, table_name: str, columns: List[str], row_start=None, row_stop=None) -> pd.DataFrame:
        injected_data = self.params.get("hbase_data", {})
        if table_name in injected_data:
            df = injected_data[table_name].copy()
            if row_start is not None:
                for period_column in ["P", "Period", "period"]:
                    if period_column in df.columns:
                        df = df[df[period_column].astype(str) == str(row_start)]
                        break
            for column in columns:
                if column not in df.columns:
                    df[column] = None
            return df[columns]
        client = self._hbase_client()
        row_prefixs = [str(index) for index in range(10)]
        df = client.query_df(
            hbase_table_name=table_name,
            columns=columns,
            row_start=row_start,
            row_stop=row_stop,
            row_prefixs=row_prefixs,
        )
        for column in columns:
            if column not in df.columns:
                df[column] = None
        return df[columns]

    def _calendar_periods(self) -> dict:
        current_date = self.current_date or datetime.datetime.now().strftime("%Y-%m-%d")
        calendar_table = "l0_cmt.date"
        calendar_columns = hbase_export_cols.get(calendar_table, ["NatureDate", "Period"])
        df_calendar = self._read_hbase_df(calendar_table, calendar_columns)
        if df_calendar.empty:
            period = str(self.params.get("period") or "")
            return {"r13p": [period] if period else [], "period": [period] if period else [], "mars_calendar": df_calendar}

        df_calendar = df_calendar.copy()
        df_calendar["NatureDate"] = df_calendar["NatureDate"].astype(str)
        calendar = df_calendar[df_calendar["NatureDate"] <= str(current_date)]
        calendar = calendar.drop_duplicates(subset="Period")
        periods = [str(value) for value in calendar["Period"].dropna().tolist()]
        # Requirement: initialization exports the 13 completed periods before the current period.
        r13p = periods[-14:-1]
        return {
            "r13p": r13p,
            "period": [r13p[-1]] if r13p else [],
            "mars_calendar": df_calendar,
        }

    def _period_list(self, time_range: dict) -> List[str]:
        specific_range = self.params.get("specific_range")
        if specific_range:
            return [str(value) for value in specific_range]
        export_mode = self.params.get("export_mode", "daily")
        # Requirement: init backfills R13P; daily mode exports only the latest completed period.
        if export_mode == "init":
            return [str(value) for value in time_range.get("r13p", []) if str(value)]
        return [str(value) for value in time_range.get("period", []) if str(value)]

    def _export_period(self, period: str) -> dict:
        table_name = self.params.get("hbase_table") or hbase_prepare_table
        columns = self.params.get("hbase_export_cols") or hbase_prepare_default_export_cols
        if not table_name or not columns:
            raise RuntimeError("Missing hbase prepare table or export columns.")
        df = self._read_hbase_df(table_name, list(columns), row_start=period, row_stop=f"{period}Z")
        input_rows = len(df)
        # Requirement: the downstream calculation consumes only configured subsegments aggregated by store.
        if "SubSegmentID" in df.columns:
            df = df[df["SubSegmentID"].astype(str).isin(hbase_prepare_subsegment_filter)]
        if "SelloutAmount" in df.columns:
            df["SelloutAmount"] = pd.to_numeric(df["SelloutAmount"], errors="coerce").fillna(0.0)
        if {"StoreID", "SelloutAmount"}.issubset(df.columns):
            df = df.groupby(["StoreID"], as_index=False).agg({"SelloutAmount": "sum"})
        logger.info(
            "transform_complete step=hbase_prepare_filter_aggregate period={} input_rows={} output_rows={}",
            period,
            input_rows,
            len(df),
        )

        file_name = f"cmt_sellout_{period}.csv.gz"
        local_dir = self.params.get("local_output_dir") or "."
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, file_name)
        df.to_csv(local_path, index=False, compression="gzip")

        fs_path = f"{self.fs_save_source_dir}/{file_name}"
        if not self.params.get("skip_fs_upload", False):
            fs_client = self._fs_client()
            fs_client.copy_from_local(local_path, fs_path, overwrite=True)
        if not self.params.get("keep_local_files", False):
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass
        logger.info("Exported HBase table={} period={} rows={} fs_path={}", table_name, period, len(df), fs_path)
        return {"period": period, "source_table": table_name, "rows": len(df), "fs_path": fs_path}

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=hbase_prepare layer=data_source")
        time_range = self._calendar_periods()
        metrics = [self._export_period(period) for period in self._period_list(time_range)]
        return {"export_metrics": pd.DataFrame(metrics)}, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")

def write_hbase_prepare_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd


class DataStorage:
    """Report HBase-prepare outputs without adding an unsupported target writer."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def run(self):
        logger.info("component_start component=hbase_prepare layer=data_storage")
        metrics = []
        for name, df in self.outputs.items():
            rows = 0 if df is None else len(df)
            logger.info("prepared output={} rows={}", name, rows)
            metrics.append({"output": name, "rows": rows, "status": "prepared"})
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")
