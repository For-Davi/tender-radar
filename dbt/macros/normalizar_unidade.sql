{#
    Forma "base" de uma unidade de medida, antes de aplicar o seed de sinônimos:
      1. maiúsculas e sem acento           "Mês"                   -> "MES"
      2. tira a sigla entre parênteses      "UNIDADE (UN)"          -> "UNIDADE"
      3. "embalagem com 1 X" é X            "EMBALAGEM 1.0 UNIDADE" -> "UNIDADE"
      4. tira ponto final e espaços extras  "UNIDADE."              -> "UNIDADE"
    translate() troca caractere por caractere; evita depender da extensão unaccent.
#}
{% macro normalizar_unidade(coluna) -%}
    trim(regexp_replace(
        regexp_replace(
            regexp_replace(
                translate(upper(trim({{ coluna }})), 'ÁÀÂÃÉÊÍÓÔÕÚÇ²', 'AAAAEEIOOOUC2'),
                '\s*\(.*\)\s*$', ''
            ),
            '^\S+\s+1(\.0+)?\s+(.+)$', '\2'
        ),
        '[.\s]+$', ''
    ))
{%- endmacro %}
