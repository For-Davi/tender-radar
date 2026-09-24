-- Reconciliação: a soma do mart mensal é igual à soma dos itens da fato.
-- Se um join ou o preenchimento de meses duplicasse ou perdesse valor, apareceria aqui.
-- Um teste singular passa quando a consulta NÃO devolve linhas.
with fato as (
    select coalesce(sum(valor_total_estimado), 0) as total
    from {{ ref('fato_contratacao_item') }}
),

mart as (
    select coalesce(sum(valor_total_estimado), 0) as total
    from {{ ref('mart_valor_contratado_mensal') }}
)

select fato.total as total_fato, mart.total as total_mart
from fato cross join mart
where abs(fato.total - mart.total) > 0.01
