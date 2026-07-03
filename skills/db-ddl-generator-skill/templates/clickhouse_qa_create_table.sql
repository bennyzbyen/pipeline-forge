CREATE TABLE {{database}}.{{table_name}}
(
{{columns}}
)
ENGINE = ReplacingMergeTree({{version_column}})
{{partition_by}}
ORDER BY ({{order_by}})
SETTINGS index_granularity = 8192;
