-- Preço por categoria mês a mês, com a variação em relação ao mês anterior (LAG).
-- GRÃO: categoria x unidade x mês. A unidade entra na partição porque "R$ 10 por
-- UNIDADE" e "R$ 10 por CAIXA" não são comparáveis.
--
-- Mediana (e não só média): um item com preço absurdo puxa a média, mas quase não
-- mexe na mediana. Itens sigilosos (preço desconhecido) ficam de fora.
with mensal as (
    select
        categoria_key,
        unidade_normalizada,
        date_trunc('month', data_publicacao)::date as mes,
        count(*) as itens,
        round(avg(valor_unitario_estimado), 4) as preco_medio,
        percentile_cont(0.5) within group (order by valor_unitario_estimado)::numeric(18, 4)
            as preco_mediano
    from {{ ref('fato_contratacao_item') }}
    where valor_unitario_estimado is not null
    group by 1, 2, 3
),

com_anterior as (
    select
        *,
        -- LAG olha a LINHA anterior da partição, que não é necessariamente o mês
        -- anterior: se março não teve itens, a linha anterior a abril é fevereiro
        lag(mes) over janela as mes_da_linha_anterior,
        lag(preco_mediano) over janela as preco_da_linha_anterior
    from mensal
    window janela as (partition by categoria_key, unidade_normalizada order by mes)
)

select
    categoria_key,
    unidade_normalizada,
    mes,
    itens,
    preco_medio,
    preco_mediano,
    -- só compara com o mês imediatamente anterior; se houve buraco, a variação é nula
    case
        when mes_da_linha_anterior = (mes - interval '1 month')::date
            then preco_da_linha_anterior
    end as preco_mediano_mes_anterior,
    case
        when mes_da_linha_anterior = (mes - interval '1 month')::date
            and preco_da_linha_anterior > 0
            then round((preco_mediano - preco_da_linha_anterior) / preco_da_linha_anterior * 100, 2)
    end as variacao_percentual
from com_anterior
