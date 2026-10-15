#!/usr/bin/env python3
"""Deterministic regressions for source types, explicit profiles and offline review."""

from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import generate_ddl as generator
import parse_existing_ddl as parser
import review_clickhouse_ddl as review


SOURCE = """CREATE TABLE `fixture_report` (
 `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
 `period` varchar(20) DEFAULT NULL,
 `code` varchar(50) DEFAULT NULL,
 `data_source` varchar(20) DEFAULT NULL,
 `amount` decimal(50,10) DEFAULT NULL COMMENT '精度与中文',
 `modified_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 PRIMARY KEY (`id`)
) ENGINE=InnoDB;"""

BASELINE = """CREATE TABLE qa_previous.fixture_report (
 `id` UInt64,
 `period` String,
 `code` String,
 `data_source` String,
 `retired` Nullable(String),
 `modified_at` DateTime DEFAULT now(),
 `cl_last_update_time` DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(cl_last_update_time)
PARTITION BY period
ORDER BY (period, code, data_source)
SETTINGS index_granularity = 4096, storage_policy = 'fixture policy';"""

AUDIT = {"name": "cl_last_update_time", "source_type": "DateTime", "nullable": False, "default": "now()"}


def run_cli(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(Path(__file__).with_name(script)), *map(str, args)],
                          encoding="utf-8", text=True, capture_output=True, check=False)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.source = parser.parse_sql(SOURCE)
        self.baseline = parser.parse_sql(BASELINE, "synthetic:qa_export#row1")

    def bound(self):
        source = copy.deepcopy(self.source)
        source["columns"].append(copy.deepcopy(AUDIT))
        return review.bind_profile(source, {"tables": [self.baseline]}, "qa_previous", "qa")

    def test_unsigned_widths_and_display_width(self):
        for source, wanted in [("tinyint(1) unsigned", "UInt8"), ("smallint unsigned", "UInt16"),
                               ("mediumint unsigned", "UInt32"), ("int(50) unsigned", "UInt32"),
                               ("bigint(20) unsigned", "UInt64"), ("int(1)", "Int32"), ("int(50)", "Int32")]:
            with self.subTest(source=source):
                self.assertEqual(generator.map_type(source, "clickhouse", {}), wanted)

    def test_precision(self):
        for source, wanted in [("decimal(50,10)", "Decimal(50, 10)"), ("decimal(18,0)", "Decimal(18, 0)"),
                               ("datetime(6)", "DateTime64(6)"), ("timestamp(3)", "DateTime64(3)")]:
            self.assertEqual(generator.map_type(source, "clickhouse", {}), wanted)
        for source in ["decimal(77,1)", "decimal(5,6)", "datetime(10)"]:
            with self.assertRaises(ValueError):
                generator.map_type(source, "clickhouse", {})

    def test_default_and_update_are_separate(self):
        modified = self.source["columns"][-1]
        self.assertEqual(modified["default"], "CURRENT_TIMESTAMP")
        self.assertEqual(modified["on_update"], "CURRENT_TIMESTAMP")
        sql, notes = generator.build_create_table(self.bound(), "clickhouse", database="qa_new", allow_key_nullability_coercion=True)
        self.assertNotIn("ON UPDATE", sql)
        self.assertTrue(any("ON UPDATE" in note for note in notes["risks"]))
        self.assertIn("AUTO_INCREMENT", " ".join(notes["risks"]))
        mysql, _ = generator.build_create_table(self.source, "mysql")
        self.assertIn("DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP", mysql)

    def test_clause_words_inside_literals(self):
        item = "`label` varchar(80) DEFAULT 'ON UPDATE NULL COMMENT' COMMENT 'NOT NULL'"
        column = parser.parse_column(item)
        self.assertEqual(column["default"], "'ON UPDATE NULL COMMENT'")
        self.assertIsNone(column["on_update"])
        self.assertTrue(column["nullable"])
        self.assertEqual(parser.extract_default("`x` int DEFAULT NULL COMMENT 'x'"), "NULL")
        self.assertEqual(parser.extract_default("`x` timestamp DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"), "CURRENT_TIMESTAMP(6)")

    def test_cot_keeps_source_immutable(self):
        original = copy.deepcopy(self.source)
        partition, order, applied = generator.apply_cot_period_code_rule(self.source, None, None)
        self.assertTrue(applied)
        self.assertEqual(self.source, original)
        with self.assertRaisesRegex(ValueError, "allow-key-nullability"):
            generator.build_create_table(self.source, "clickhouse", partition_by=partition, order_by=order, clickhouse_engine="MergeTree")

    def test_explicit_and_profile_keys_win(self):
        schema = self.bound()
        self.assertFalse(generator.apply_cot_period_code_rule(schema, None, None)[2])
        sql, _ = generator.build_create_table(schema, "clickhouse", database="qa_new", allow_key_nullability_coercion=True)
        self.assertIn("ORDER BY (period, code, data_source)", sql)
        self.assertNotIn("PRIMARY KEY", sql)
        self.assertIn("index_granularity = 4096", sql)
        self.assertIn("storage_policy = 'fixture policy'", sql)
        sql, _ = generator.build_create_table(schema, "clickhouse", order_by=["id"], partition_by=[],
                                             clickhouse_engine="MergeTree", clickhouse_table_settings={})
        self.assertIn("ORDER BY (id)", sql)
        self.assertNotIn("PARTITION BY", sql)
        self.assertNotIn("SETTINGS", sql)

    def test_version_is_never_guessed(self):
        schema = copy.deepcopy(self.source)
        for engine in ["ReplacingMergeTree", "ReplacingMergeTree()", "ReplicatedReplacingMergeTree"]:
            with self.subTest(engine=engine), self.assertRaisesRegex(ValueError, "version"):
                generator.build_create_table(schema, "clickhouse", order_by=["id"], clickhouse_engine=engine)
        self.assertIsNone(generator.choose_version_column(schema["columns"]))
        schema["columns"].append({"name": "signed_version", "type": "bigint", "nullable": False})
        for version in ["missing", "period", "signed_version"]:
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "version"):
                generator.build_create_table(schema, "clickhouse", order_by=["id"], clickhouse_engine="ReplacingMergeTree", clickhouse_version_column=version)

    def test_valid_embedded_version(self):
        schema = self.bound()
        sql, _ = generator.build_create_table(schema, "clickhouse", clickhouse_engine="ReplacingMergeTree(cl_last_update_time)", allow_key_nullability_coercion=True)
        self.assertIn("ReplacingMergeTree(cl_last_update_time)", sql)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            generator.build_create_table(schema, "clickhouse", clickhouse_engine="ReplacingMergeTree(modified_at)",
                clickhouse_version_column="cl_last_update_time", allow_key_nullability_coercion=True)
        sql, _ = generator.build_create_table(schema, "clickhouse", clickhouse_engine="ReplacingMergeTree(modified_at)", allow_key_nullability_coercion=True)
        self.assertIn("ReplacingMergeTree(modified_at)", sql)

    def test_fractional_timestamp_default(self):
        self.assertEqual(generator.normalize_default("CURRENT_TIMESTAMP(6)", "clickhouse"), "now64(6)")
        schema = {"columns": [{"name": "v", "source_type": "timestamp(6)", "nullable": False, "default": "CURRENT_TIMESTAMP(6)"}]}
        sql, _ = generator.build_create_table(schema, "clickhouse", order_by=["v"], clickhouse_engine="ReplacingMergeTree", clickhouse_version_column="v")
        self.assertIn("DateTime64(6) DEFAULT now64(6)", sql)

    def test_profile_binding_is_exact_and_env_specific(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            review.bind_profile(self.source, {"tables": [self.baseline]}, "wrong_db", "qa")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            review.bind_profile(self.source, {"tables": [self.baseline, self.baseline]}, "qa_previous", "qa")
        with self.assertRaises(ValueError):
            generator.build_create_table(self.bound(), "clickhouse", env="prod", order_by=["id"])

    def test_replication_path_not_carried_to_new_database(self):
        baseline = copy.deepcopy(self.baseline)
        baseline["engine"] = "ReplicatedReplacingMergeTree('/fixture/qa_previous/{shard}/fixture_report', '{custom_replica}', cl_last_update_time)"
        schema = review.bind_profile(self.bound(), {"tables": [baseline]}, "qa_previous", "prod")
        with self.assertRaisesRegex(ValueError, "new replication path"):
            generator.build_create_table(schema, "clickhouse", env="prod", database="new_db", allow_key_nullability_coercion=True)
        sql, _ = generator.build_create_table(schema, "clickhouse", env="prod", database="new_db",
            clickhouse_replication_path="/fixture/new_db/{shard}/fixture_report", allow_key_nullability_coercion=True)
        self.assertIn("'{custom_replica}'", sql)
        self.assertIn("/fixture/new_db/", sql)

    def test_expression_keys_and_nullable_inputs(self):
        schema = self.bound()
        with self.assertRaisesRegex(ValueError, "allow-key-nullability"):
            generator.build_create_table(schema, "clickhouse", order_by=["ifNull(code, '')"])
        sql, _ = generator.build_create_table(schema, "clickhouse", order_by=["id"], partition_by=[])
        self.assertIn("`code` Nullable(String)", sql)
        self.assertEqual(generator.split_csv("tuple(period, code),id"), ["tuple(period, code)", "id"])
        round_trip = parser.parse_sql(sql.replace("ORDER BY (id)", "ORDER BY (tuple(period, code), id)"))
        self.assertEqual(round_trip["order_by"], ["tuple(period, code)", "id"])

    def test_unknown_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown.*key"):
            generator.build_create_table(self.bound(), "clickhouse", order_by=["missing"])

    def test_diff_covers_changes_beyond_count(self):
        old = copy.deepcopy(self.baseline)
        new = copy.deepcopy(old)
        new["columns"][0]["source_type"] = "Int64"
        new["columns"][1]["nullable"] = True
        new["columns"][2]["comment"] = "changed"
        new["columns"][3]["default"] = "'a b'"
        new["columns"][4]["name"] = "new_field"
        new["columns"][0], new["columns"][1] = new["columns"][1], new["columns"][0]
        new["order_by"] = ["id", "period"]
        new["table_settings"]["index_granularity"] = "8192"
        diff = review.compare_schemas(old, new)
        self.assertEqual(diff["added"], ["new_field"])
        self.assertEqual(diff["removed"], ["retired"])
        self.assertTrue(diff["common_column_order_changed"])
        self.assertEqual(len(diff["column_changes"]), 4)
        self.assertEqual(len(diff["configuration_changes"]), 2)
        self.assertNotEqual(review.normalize_expression("'a b'"), review.normalize_expression("'ab'"))

    def test_scope_requires_complete_decisions(self):
        other = copy.deepcopy(self.source)
        other["table_name"] = "not_needed"
        entries = {"tables": [{"database": None, "table_name": "fixture_report", "action": "create", "reason": "target mapping"},
                              {"database": None, "table_name": "not_needed", "action": "skip", "reason": "no target"}]}
        selected = review.apply_scope([self.source, other], entries)
        self.assertEqual([s["table_name"] for s in selected], ["fixture_report"])
        with self.assertRaises(ValueError):
            review.apply_scope([self.source], entries)

    def test_full_cli_review_and_tamper_detection(self):
        with tempfile.TemporaryDirectory(prefix="ddl_review_") as temp:
            root = Path(temp)
            source, baseline, schema, target, audit, record = [root / n for n in ["source.sql", "qa.csv", "schema.json", "target.sql", "audit.json", "review.json"]]
            source.write_text(SOURCE, encoding="utf-8")
            audit.write_text(json.dumps({"columns": [AUDIT]}), encoding="utf-8")
            with baseline.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["database", "table_name", "ddl"])
                writer.writeheader()
                writer.writerow({"database": "qa_previous", "table_name": "fixture_report", "ddl": BASELINE})
            source_schema = copy.deepcopy(self.source)
            source_schema["columns"].append(copy.deepcopy(AUDIT))
            schema.write_text(json.dumps(source_schema), encoding="utf-8")
            generated = run_cli("generate_ddl.py", schema, "--target", "clickhouse", "--database", "qa_new", "--deployment-export", baseline,
                                "--profile-database", "qa_previous", "--cot-period-code-rule", "--allow-key-nullability-coercion", "--sql-only", "--output", target)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            arguments = ["--source", source, "--target", target, "--baseline", baseline, "--baseline-database", "qa_previous", "--env", "qa",
                         "--audit-schema", audit, "--allow-key-nullability-coercion", "--output", record]
            completed = run_cli("review_clickhouse_ddl.py", *arguments)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            data = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(data["counts"], {"source": 6, "audit": 1, "target": 7})
            self.assertEqual(data["baseline_diff"]["added"], ["amount"])
            self.assertEqual(data["baseline_diff"]["removed"], ["retired"])
            self.assertEqual(data["stage"], "offline_reconciled")
            self.assertEqual(len(data["inputs"]), 4)
            target.write_text(target.read_text(encoding="utf-8").replace("UInt64", "Int64"), encoding="utf-8")
            completed = run_cli("review_clickhouse_ddl.py", *arguments)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["status"], "FAIL")
            # A duplicate baseline must fail, rather than select an arbitrary row.
            with baseline.open("a", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(["qa_previous", "fixture_report", BASELINE])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                parser.parse_csv_export(baseline)


if __name__ == "__main__":
    unittest.main(verbosity=2)
