"""Vehicle-verification storage scaffold writer."""

from __future__ import annotations

from pathlib import Path


def write_vehicle_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import os

from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map
from params_configs.db_config import clickhouse_connect_params, cluster


try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None


class DataStorage:
    """Replace vehicle-verification ClickHouse outputs by reporting period."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params
        self.period = str(time_range.get("P") or time_range.get("period") or "").strip()

    def _get_clickhouse_client(self):
        injected_client = self.params.get("clickhouse_client")
        if injected_client is not None:
            return injected_client
        if clickhouse_connect is None:
            raise RuntimeError("clickhouse_connect is not installed and no clickhouse_client was supplied.")
        if clickhouse_connect_params.get("CLICKHOUSE_HOST", "").startswith("<"):
            raise RuntimeError("ClickHouse connection placeholders must be filled before deployment.")
        return clickhouse_connect.get_client(
            host=clickhouse_connect_params["CLICKHOUSE_HOST"],
            port=int(clickhouse_connect_params["CLICKHOUSE_PORT"]),
            user=clickhouse_connect_params["CLICKHOUSE_USER"],
            password=clickhouse_connect_params["CLICKHOUSE_PASSWORD"],
            database=clickhouse_connect_params["CLICKHOUSE_DB"],
        )

    def _delete_period(self, client, table_name: str):
        if not self.period:
            raise ValueError("time_range must provide P or period before writing ClickHouse targets.")
        # Safety: period replacement deletes stale rows before inserting the complete non-empty output.
        delete_sql = f"ALTER TABLE {table_name} {cluster} DELETE WHERE period = '{self.period}'"
        logger.info("target_replace storage=clickhouse target={} predicate=period period={}", table_name, self.period)
        client.command(delete_sql)

    def _insert_dataframe(self, client, table_name: str, df: pd.DataFrame):
        logger.info("Inserting ClickHouse table={} rows={}", table_name, len(df))
        if hasattr(client, "insert_df"):
            client.insert_df(table_name, df)
            return
        if hasattr(client, "insert_dataframe"):
            client.insert_dataframe(table_name, df)
            return
        raise RuntimeError("ClickHouse client must support insert_df or insert_dataframe.")

    def _replace_period(self, client, target_name: str, df: pd.DataFrame):
        table_name = target_table_map.get(target_name, target_name)
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} target={} reason=empty_output", target_name, table_name)
            return {"target": table_name, "rows": 0, "status": "skipped_empty"}
        self._delete_period(client, table_name)
        self._insert_dataframe(client, table_name, df)
        return {"target": table_name, "rows": len(df), "status": "inserted"}

    def run(self):
        logger.info("component_start component=vehicle layer=data_storage")
        client = self._get_clickhouse_client()
        metrics = []
        for target_name, df in self.outputs.items():
            metrics.append(self._replace_period(client, target_name, df))
        return metrics
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")
