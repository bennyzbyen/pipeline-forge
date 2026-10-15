CREATE TABLE {{database}}.{{table_name}} {{confirmed_on_cluster_clause}}
(
{{columns}}
)
ENGINE = {{confirmed_engine_expression}}
{{partition_by}}
ORDER BY ({{order_by}})
{{primary_key}}
{{confirmed_settings_clause}};
