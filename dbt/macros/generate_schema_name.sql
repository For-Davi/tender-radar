{#
    Por padrão, o dbt junta o schema do profile com o da pasta: "gold_staging".
    Aqui usamos o nome da pasta como está ("staging", "gold"), que é mais legível
    para quem consulta o banco (API, dbt docs, psql).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
