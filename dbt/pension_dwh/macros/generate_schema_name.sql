{#-
  Custom generate_schema_name macro.

  dbt default behavior:
    If a model has +schema: foo,   schema = "{target.schema}_foo"  (i.e. DBT_DEV_foo)
    If a model has no schema cfg,  schema = "{target.schema}"      (i.e. DBT_DEV)

  We want:
    If a model has +schema: foo,   schema = "foo"                   (i.e. stg_oncap directly)
    If a model has no schema cfg,  schema = "{target.schema}"       (i.e. DBT_DEV fallback)

  Why: our raw_oncap / stg_oncap / mart_oncap layers are explicit Snowflake
  schemas, not dev-suffixed namespaces. Default behavior would land
  staging models in "DBT_DEV_stg_oncap" instead of "stg_oncap".

  Source: https://docs.getdbt.com/docs/build/custom-schemas
-#}

{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- if custom_schema_name is none -%}

        {{ target.schema }}

    {%- else -%}

        {{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}