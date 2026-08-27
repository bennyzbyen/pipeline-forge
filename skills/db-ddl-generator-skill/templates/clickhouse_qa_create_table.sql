CREATE TABLE {{database}}.{{table_name}}
(
{{columns}}
)
ENGINE = {{confirmed_engine_expression}}
{{partition_by}}
ORDER BY ({{order_by}})
SETTINGS index_granularity = 8192;
