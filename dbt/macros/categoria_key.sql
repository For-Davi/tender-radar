{#
    Chave da categoria: usada na dim_categoria e na fato, que precisam gerar
    exatamente o mesmo valor. coalesce: md5 de NULL é NULL, e a chave não pode ser nula.
#}
{% macro categoria_key(material_ou_servico, ncm_capitulo) -%}
    md5({{ material_ou_servico }} || '|' || coalesce({{ ncm_capitulo }}, '--'))
{%- endmacro %}
