"""Fallback scaffold writers for review-only or incomplete plans."""

from __future__ import annotations

from pathlib import Path


def write_generic_data_process(target: Path, outputs: list[str]) -> None:
    content = f'''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import field_rules, target_table_columns


class DataProcess:
    """Placeholder transformation contract for plan-driven report outputs."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=report layer=data_process")
        for target_name in {outputs!r}:
            logger.info("planned output {{}} fields={{}}", target_name, len(field_rules.get(target_name, [])))
        raise NotImplementedError(
            "Report scaffold only: implement source cleaning, joins, KPI formulas, "
            "aggregations, and final column ordering before deployment. "
            "See IMPLEMENTATION_STATUS.md and params_configs/col_config.py."
        )
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")

def write_generic_data_source(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, List, Optional, Tuple, logger, pd
from params_configs.col_config import fs_source_config, hbase_export_cols, hbase_export_range


class DataSource:
    """Placeholder source contract for a plan-driven report component."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        return {
            "current_date": self.params.get("current_date", ""),
            "period": self.params.get("period", ""),
            "P": self.params.get("period", ""),
        }

    def _read_hbase(self, table_name: str, columns: List[str], fetch_range: dict, time_range: dict) -> pd.DataFrame:
        logger.info("planned HBase read table={} columns={} range={}", table_name, len(columns), fetch_range)
        return pd.DataFrame(columns=columns)

    def _read_fs(self, key: str, config: dict, time_range: dict) -> pd.DataFrame:
        logger.info("planned FS read key={} path={} columns={}", key, config.get("path"), len(config.get("fields", [])))
        return pd.DataFrame(columns=config.get("fields", []))

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=report layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        for table_name, columns in hbase_export_cols.items():
            source_data[table_name] = self._read_hbase(table_name, columns, hbase_export_range.get(table_name, {}), time_range)
        for key, config in fs_source_config.items():
            source_data[key] = self._read_fs(key, config, time_range)
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")

def write_generic_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from params_configs.col_config import target_table_map


class DataStorage:
    """Placeholder storage contract for plan-driven report outputs."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def run(self):
        logger.info("component_start component=report layer=data_storage")
        for target_name, df in self.outputs.items():
            physical_table = target_table_map.get(target_name, target_name)
            logger.info("planned ClickHouse write target={} physical={} rows={}", target_name, physical_table, len(df))
        raise NotImplementedError(
            "Report scaffold only: implement ClickHouse delete/insert and any FS evidence writes before deployment."
        )
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")
