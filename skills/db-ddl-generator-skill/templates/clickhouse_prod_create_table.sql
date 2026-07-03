CREATE TABLE {{database}}.{{table_name}} ON CLUSTER cl_1shards_2replicas
(
{{columns}}
)
ENGINE = ReplicatedReplacingMergeTree('/clickhouse/databases/{{database}}/tables/{shard_name}/{{table_name}}', '{replica}', {{version_column}})
{{partition_by}}
ORDER BY ({{order_by}})
{{primary_key}}
SETTINGS index_granularity = 8192;
