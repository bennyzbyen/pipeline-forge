"""Vehicle-verification source scaffold writer."""

from __future__ import annotations

from pathlib import Path


def write_vehicle_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from common_utils.all_modules import logger, pd
from gateway.client import GateWayClient
from params_configs.col_config import fs_source_config, hbase_export_cols, hbase_export_range
from params_configs.db_config import app_key, app_secret, env, fs_root_dir


class DataSource:
    """Read vehicle-verification sources for the resolved reporting range."""

    def __init__(self, params: dict):
        self.params = params
        self.period = params.get("period")
        self.current_date = params.get("current_date")

    def _gateway_client(self):
        if self.params.get("gateway_client") is not None:
            return self.params["gateway_client"]
        return GateWayClient(app_key, app_secret, env=env)

    def _hbase_client(self):
        if self.params.get("hbase_client") is not None:
            return self.params["hbase_client"]
        client = self._gateway_client()
        try:
            return client.getHbaseClient(fs_root_dir=fs_root_dir)
        except TypeError:
            return client.getHbaseClient()

    def _fs_client(self):
        if self.params.get("fs_client") is not None:
            return self.params["fs_client"]
        return self._gateway_client().getFsClient()

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
            hbase_client = self._hbase_client()
            df = hbase_client.query_df(
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
        return df[columns]

    def _target_p_from_param(self, period: str) -> Tuple[str, str]:
        value = str(period or "").strip()
        if not value:
            return "", ""
        if "P" in value:
            target_p = value
            target_period = value.replace("P", "")
        elif len(value) >= 6:
            target_period = value
            target_p = f"{value[:4]}P{value[-2:]}"
        else:
            target_p = value
            target_period = value.replace("P", "")
        return target_p, target_period

    def get_period_details(self, calendar_df: pd.DataFrame, period=None) -> dict:
        required = ["dataid", "m_year", "m_period"]
        for column in required:
            if column not in calendar_df.columns:
                raise ValueError(f"mars_calendar missing required column: {column}")
        calendar_df = calendar_df[required].copy()
        calendar_df["dataid"] = calendar_df["dataid"].astype(str)
        calendar_df["p"] = calendar_df["m_year"].astype(str) + "P" + calendar_df["m_period"].astype(str).str.zfill(2)

        if period:
            target_p, target_period = self._target_p_from_param(period)
        else:
            current_date = str(self.current_date or datetime.datetime.now().strftime("%Y%m%d"))
            current_rows = calendar_df.loc[calendar_df["dataid"] == current_date]
            if current_rows.empty:
                raise ValueError(f"mars_calendar has no current_date row: {current_date}")
            current_p = current_rows["p"].iloc[0]
            periods = calendar_df[["p"]].drop_duplicates().sort_values("p").reset_index(drop=True)
            periods["prev_p"] = periods["p"].shift(1)
            matched = periods.loc[periods["p"] == current_p]
            if matched.empty or pd.isna(matched["prev_p"].iloc[0]):
                raise ValueError(f"Cannot derive previous period from current period: {current_p}")
            target_p = matched["prev_p"].iloc[0]
            target_period = target_p.replace("P", "")

        period_rows = calendar_df.loc[calendar_df["p"] == target_p]
        if period_rows.empty:
            raise ValueError(f"mars_calendar has no rows for target period: {target_p}")
        time_range = {
            "P": target_p,
            "period": target_period,
            "p_start_date": period_rows["dataid"].min(),
            "p_end_date": period_rows["dataid"].max(),
        }
        logger.info(
            "time_range_resolved component=vehicle period={} P={} start={} end={}",
            time_range.get("period"),
            time_range.get("P"),
            time_range.get("p_start_date"),
            time_range.get("p_end_date"),
        )
        return time_range

    def _read_calendar(self) -> Tuple[pd.DataFrame, dict]:
        columns = hbase_export_cols.get("l0_mdp.mars_calendar", ["dataid", "m_year", "m_period"])
        calendar_df = self.read_hbase_2_df("l0_mdp.mars_calendar", columns)
        time_range = self.get_period_details(calendar_df, period=self.period)
        return calendar_df, time_range

    def _range_value(self, time_range: dict, key):
        if key is None:
            return None
        return time_range.get(str(key), str(key))

    def _read_hbase_with_range(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        start_key = fetch_range.get("start_time")
        end_key = fetch_range.get("end_time")
        row_start = self._range_value(time_range, start_key)
        row_stop = self._range_value(time_range, end_key)
        row_prefixs = None
        if fetch_range.get("row_prefixs") or fetch_range.get("is_row_prefixs"):
            row_prefixs = [str(index) for index in range(10)]
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

    def fetch_hbase_tables(self, time_range: dict, calendar_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        df_map: Dict[str, pd.DataFrame] = {"l0_mdp.mars_calendar": calendar_df}
        for table_name, columns in hbase_export_cols.items():
            if table_name == "l0_mdp.mars_calendar":
                continue
            df_map[table_name] = self._read_hbase_with_range(
                table_name,
                columns,
                hbase_export_range.get(table_name, {}),
                time_range,
            )
            logger.info("HBase table={} rows={}", table_name, len(df_map[table_name]))
        return df_map

    def _safe_read_csv(self, fs_client, fs_path: str, local_dir: str, columns: List[str]) -> Optional[pd.DataFrame]:
        file_name = os.path.basename(fs_path)
        local_path = os.path.join(local_dir, file_name)
        try:
            fs_client.copy_to_local(fs_path, local_path)
            return pd.read_csv(local_path, sep="\\t", dtype=str, usecols=columns, engine="c", low_memory=False)
        except Exception as exc:
            logger.error("Failed to process FS file {}: {}", fs_path, exc)
            return None
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    def _render_fs_path(self, path: str, time_range: dict) -> str:
        return (
            str(path or "")
            .replace("{Period}", time_range.get("P", ""))
            .replace("{period}", time_range.get("period", ""))
            .replace("{P}", time_range.get("P", ""))
        )

    def fetch_fs_data(self, time_range: dict) -> Dict[str, pd.DataFrame]:
        injected = self.params.get("fs_data", {})
        df_fs_map: Dict[str, pd.DataFrame] = {}
        fs_client = None
        for key, config in fs_source_config.items():
            columns = list(config.get("fields", []))
            if key in injected:
                df = injected[key].copy()
                for column in columns:
                    if column not in df.columns:
                        df[column] = None
                df_fs_map[key] = df[columns] if columns else df
                logger.info("Loaded injected FS data key={} rows={}", key, len(df_fs_map[key]))
                continue

            if fs_client is None:
                fs_client = self._fs_client()
            fs_dir = self._render_fs_path(config.get("path", ""), time_range)
            logger.info("Reading FS key={} path={} columns={}", key, fs_dir, len(columns))
            if hasattr(fs_client, "exists") and not fs_client.exists(fs_dir):
                logger.warning("FS path does not exist: {}", fs_dir)
                df_fs_map[key] = pd.DataFrame(columns=columns)
                continue
            with tempfile.TemporaryDirectory() as tmp_dir:
                files = fs_client.listdir(fs_dir)
                frames = []
                for file_name in files:
                    fs_path = f"{fs_dir.rstrip('/')}/{file_name}"
                    df = self._safe_read_csv(fs_client, fs_path, tmp_dir, columns)
                    if df is not None and not df.empty:
                        frames.append(df)
                df_fs_map[key] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
                logger.info("FS key={} rows={}", key, len(df_fs_map[key]))
        return df_fs_map

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=vehicle layer=data_source")
        calendar_df, time_range = self._read_calendar()
        source_data: Dict[str, pd.DataFrame] = {}
        source_data.update(self.fetch_hbase_tables(time_range, calendar_df))
        source_data.update(self.fetch_fs_data(time_range))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")
