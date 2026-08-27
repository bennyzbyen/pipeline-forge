"""Validated execution-contract scaffold writers."""

from __future__ import annotations

from pathlib import Path


def write_contract_data_process(target: Path) -> None:
    content = '''# coding: utf-8
from common_utils.all_modules import Dict, logger, pd
from data_utils.contract_runtime import execute_contract
from params_configs.execution_contract import execution_contract


class DataProcess:
    """Execute a validated, normalized report transformation contract."""

    def __init__(self, source_data: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.source_data = source_data
        self.time_range = time_range
        self.params = params

    def run(self) -> Dict[str, pd.DataFrame]:
        logger.info("component_start component=contract_report layer=data_process")
        return execute_contract(self.source_data, self.time_range, self.params, execution_contract)
'''
    (target / "data_utils" / "data_process.py").write_text(content, encoding="utf-8")

def write_contract_data_source(target: Path) -> None:
    content = '''# coding: utf-8
import datetime
import os
import tempfile

from common_utils.all_modules import Dict, List, Tuple, logger, pd
from gateway.client import GateWayClient
from params_configs.db_config import app_key, app_secret, env, fs_root_dir
from params_configs.execution_contract import execution_contract


class DataSource:
    """Load normalized contract sources through explicit adapters or injected fixtures."""

    def __init__(self, params: dict):
        self.params = params

    def _resolve_time_range(self) -> dict:
        current_date = str(self.params.get("current_date") or datetime.datetime.now().strftime("%Y-%m-%d"))
        period = str(self.params.get("period") or self.params.get("P") or "")
        values = {"current_date": current_date, "period": period, "P": str(self.params.get("P") or period)}
        values.update(self.params.get("time_range") or {})
        return values

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

    def _injected(self, source_name: str, config: dict):
        location = str(config.get("location") or source_name)
        for container_name in ["source_data", f"{config.get('kind')}_data"]:
            container = self.params.get(container_name) or {}
            if source_name in container:
                return container[source_name].copy()
            if location in container:
                return container[location].copy()
        return None

    def _normalize(self, source_name: str, config: dict, df: pd.DataFrame) -> pd.DataFrame:
        columns = list(config.get("columns") or [])
        if df is None:
            return pd.DataFrame(columns=columns)
        missing = [column for column in columns if column not in df.columns]
        if missing:
            raise ValueError(f"source {source_name} missing configured columns: {missing}")
        return df.loc[:, columns].copy()

    def _range_value(self, value, time_range: dict):
        if value is None:
            return None
        text = str(value)
        if text.startswith("time_range."):
            key = text.split(".", 1)[1]
            if key not in time_range:
                raise ValueError(f"source range key is missing: {text}")
            return time_range[key]
        if text.startswith("params."):
            key = text.split(".", 1)[1]
            if key not in self.params:
                raise ValueError(f"source range key is missing: {text}")
            return self.params[key]
        return value

    def _read_hbase(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        fetch_range = config.get("range") or {}
        row_start = self._range_value(fetch_range.get("start"), time_range)
        row_stop = self._range_value(fetch_range.get("stop"), time_range)
        row_prefixs = fetch_range.get("row_prefixs")
        logger.info("source_read_start storage=hbase source={} columns={} ranged={}", source_name, len(config.get("columns") or []), bool(row_start or row_stop))
        df = self._hbase_client().query_df(
            hbase_table_name=config["location"],
            columns=list(config.get("columns") or []),
            row_start=row_start,
            row_stop=row_stop,
            row_prefixs=row_prefixs,
        )
        return self._normalize(source_name, config, df)

    def _render_path(self, path: str, time_range: dict) -> str:
        result = str(path or "")
        for key, value in time_range.items():
            result = result.replace("{" + str(key) + "}", str(value))
        return result

    def _read_fs(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        fs_client = self._fs_client()
        fs_path = self._render_path(config["location"], time_range)
        file_format = str(config.get("format") or "csv").lower()
        separator = str(config.get("separator") or ("\\t" if file_format in {"tsv", "txt"} else ","))
        remote_files = fs_client.listdir(fs_path) if hasattr(fs_client, "listdir") else [fs_path]
        frames = []
        with tempfile.TemporaryDirectory() as temp_dir:
            for remote_name in remote_files:
                remote_name = str(remote_name)
                remote_path = remote_name if remote_name.startswith("/") else f"{fs_path.rstrip('/')}/{remote_name}"
                local_path = os.path.join(temp_dir, os.path.basename(remote_path))
                fs_client.copy_to_local(remote_path, local_path)
                if file_format == "parquet":
                    frame = pd.read_parquet(local_path, columns=list(config.get("columns") or []))
                else:
                    frame = pd.read_csv(local_path, sep=separator, usecols=list(config.get("columns") or []), low_memory=False)
                frames.append(frame)
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=config.get("columns") or [])
        return self._normalize(source_name, config, df)

    def _read_callable(self, source_name: str, config: dict, time_range: dict) -> pd.DataFrame:
        injected = self._injected(source_name, config)
        if injected is not None:
            return self._normalize(source_name, config, injected)
        reader_name = f"{config.get('kind')}_reader"
        reader = self.params.get(reader_name)
        if not callable(reader):
            raise RuntimeError(f"source {source_name} requires callable params[{reader_name!r}] or injected data")
        return self._normalize(source_name, config, reader(config, time_range))

    def run(self) -> Tuple[Dict[str, pd.DataFrame], dict]:
        logger.info("component_start component=contract_report layer=data_source")
        time_range = self._resolve_time_range()
        source_data: Dict[str, pd.DataFrame] = {}
        for source_name, config in (execution_contract.get("sources") or {}).items():
            kind = config.get("kind")
            if kind == "injected":
                df = self._injected(source_name, config)
                if df is None:
                    raise RuntimeError(f"injected source is required: {source_name}")
                source_data[source_name] = self._normalize(source_name, config, df)
            elif kind == "hbase":
                source_data[source_name] = self._read_hbase(source_name, config, time_range)
            elif kind == "fs":
                source_data[source_name] = self._read_fs(source_name, config, time_range)
            elif kind in {"mssql", "mysql"}:
                source_data[source_name] = self._read_callable(source_name, config, time_range)
            else:
                raise ValueError(f"unsupported source kind: {kind}")
            logger.info("source_read_complete source={} rows={} columns={}", source_name, len(source_data[source_name]), len(source_data[source_name].columns))
        return source_data, time_range
'''
    (target / "data_utils" / "data_source.py").write_text(content, encoding="utf-8")

def write_contract_data_storage(target: Path) -> None:
    content = '''# coding: utf-8
import re
import tempfile
from pathlib import Path

from common_utils.all_modules import Dict, logger, pd
from params_configs.execution_contract import execution_contract


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*$")


class DataStorage:
    """Write contract outputs with explicit append or replace predicates."""

    def __init__(self, outputs: Dict[str, pd.DataFrame], time_range: dict, params: dict):
        self.outputs = outputs
        self.time_range = time_range
        self.params = params

    def _client(self):
        client = self.params.get("clickhouse_client")
        if client is None:
            raise RuntimeError("A clickhouse_client must be supplied for contract report writes.")
        return client

    def _identifier(self, value: str) -> str:
        value = str(value or "")
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"unsafe SQL identifier in execution contract: {value!r}")
        return value

    def _value_from(self, value_from: str):
        root, _, key = str(value_from or "").partition(".")
        values = self.time_range if root == "time_range" else self.params if root == "params" else None
        if values is None or not key or key not in values:
            raise ValueError(f"write predicate value is missing: {value_from!r}")
        return values[key]

    def _literal(self, value) -> str:
        if value is None:
            raise ValueError("replace predicate value cannot be null")
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    def _command(self, client, sql: str):
        logger.info("target_command storage=clickhouse operation={} statement_length={}", sql.split(maxsplit=1)[0], len(sql))
        if hasattr(client, "command"):
            return client.command(sql)
        if hasattr(client, "execute"):
            return client.execute(sql)
        raise RuntimeError("clickhouse_client must provide command(sql) or execute(sql)")

    def _insert(self, client, table: str, df: pd.DataFrame):
        if hasattr(client, "insert_df"):
            return client.insert_df(table, df)
        if hasattr(client, "insert_dataframe"):
            return client.insert_dataframe(table, df)
        raise RuntimeError("clickhouse_client must provide insert_df(table, df) or insert_dataframe(table, df)")

    def _prepare(self, output_name: str, df: pd.DataFrame, write: dict) -> pd.DataFrame:
        columns = list(write.get("columns") or [])
        column_types = list(write.get("column_types") or [])
        missing = [column for column in columns if column not in df.columns]
        if missing:
            raise ValueError(f"output {output_name} is missing target columns: {missing}")
        if len(columns) != len(column_types):
            raise ValueError(f"output {output_name} target columns/types are not aligned")
        prepared = df.loc[:, columns].copy()
        for column, target_type in zip(columns, column_types):
            normalized_type = str(target_type or "").lower().replace("nullable(", "").rstrip(")")
            if normalized_type.startswith(("int", "uint")):
                numeric = pd.to_numeric(prepared[column], errors="coerce")
                invalid = prepared[column].notna() & numeric.isna()
                fractional = numeric.notna() & ((numeric % 1) != 0)
                if invalid.any() or fractional.any():
                    raise ValueError(f"{output_name}.{column} requires integer-compatible values")
                prepared[column] = numeric.map(lambda value: None if pd.isna(value) else str(int(value)))
            elif normalized_type.startswith("datetime"):
                parsed = pd.to_datetime(prepared[column], errors="coerce")
                invalid = prepared[column].notna() & parsed.isna()
                if invalid.any():
                    raise ValueError(f"{output_name}.{column} requires datetime-compatible values")
                prepared[column] = parsed.map(lambda value: None if pd.isna(value) else value.strftime("%Y-%m-%d %H:%M:%S"))
        return prepared

    def _insert_file(self, client, table: str, df: pd.DataFrame, write: dict):
        wire = write.get("staging_wire_format") or {}
        columns = list(write.get("columns") or [])
        insert_file_fn = self.params.get("clickhouse_insert_file")
        if insert_file_fn is None:
            from clickhouse_connect.driver.tools import insert_file as insert_file_fn
        database, _, table_name = table.partition(".")
        if not table_name:
            database, table_name = None, database
        with tempfile.TemporaryDirectory(prefix="pipelineforge_clickhouse_") as temp_dir:
            path = Path(temp_dir) / f"{table_name}.csv"
            df.to_csv(
                path,
                index=False,
                header=False,
                encoding="utf-8",
                na_rep="\\\\N",
                lineterminator="\\n",
            )
            raw = path.read_bytes()
            if raw.startswith(b"\\xef\\xbb\\xbf"):
                raise ValueError("ClickHouse staging CSV must not contain a UTF-8 BOM")
            return insert_file_fn(
                client,
                table_name,
                str(path),
                column_names=columns,
                database=database,
                settings={"input_format_allow_errors_ratio": 0, "input_format_allow_errors_num": 0},
            )

    def _write_one(self, client, output_name: str, df: pd.DataFrame, write: dict):
        table = self._identifier(write.get("table"))
        if df is None or df.empty:
            logger.info("stage_skip stage=data_storage output={} reason=empty_output", output_name)
            return {"output": output_name, "target": table, "rows": 0, "status": "skipped_empty"}
        prepared = self._prepare(output_name, df, write)
        mode = write.get("mode")
        if mode == "replace_where":
            predicate = write.get("predicate") or {}
            column = self._identifier(predicate.get("column"))
            value = self._value_from(predicate.get("value_from"))
            sql = f"ALTER TABLE {table} DELETE WHERE {column} = {self._literal(value)}"
            self._command(client, sql)
        elif mode != "append":
            raise ValueError(f"unsupported write mode: {mode}")
        logger.info("target_insert storage=clickhouse output={} target={} rows={}", output_name, table, len(df))
        if write.get("transport") == "insert_file":
            self._insert_file(client, table, prepared, write)
        else:
            self._insert(client, table, prepared)
        return {"output": output_name, "target": table, "rows": len(df), "status": "inserted", "mode": mode}

    def run(self):
        logger.info("component_start component=contract_report layer=data_storage")
        client = self._client()
        writes = execution_contract.get("writes") or {}
        return [self._write_one(client, name, self.outputs[name], writes[name]) for name in writes]
'''
    (target / "data_utils" / "data_storage.py").write_text(content, encoding="utf-8")
