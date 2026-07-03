CREATE TABLE demo_db.demo_order ON CLUSTER cl_1shards_2replicas
(
    `id` Int64 COMMENT 'primary id',
    `period` String COMMENT 'period',
    `amount` Nullable(Decimal(18, 2)) COMMENT 'amount',
    `updated_at` DateTime DEFAULT now() COMMENT 'last update time'
)
ENGINE = ReplicatedReplacingMergeTree('/clickhouse/databases/demo_db/tables/{shard_name}/demo_order', '{replica}', updated_at)
PARTITION BY period
ORDER BY (period, id)
SETTINGS index_granularity = 8192;
