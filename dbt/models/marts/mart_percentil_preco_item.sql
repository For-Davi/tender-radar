-- Posição do preço de cada item entre os itens comparáveis (PERCENT_RANK).
-- GRÃO: 1 linha por item com preço estimado conhecido. Base do alerta de sobrepreço
-- (Etapa 09).
--
-- PERCENT_RANK = (posição - 1) / (total da partição - 1): 0 = mais barato,
-- 1 = mais caro. "Comparável" = mesma categoria E mesma unidade.
with ranqueados as (
    select
        item_key,
        numero_controle_pncp,
        numero_item,
        orgao_key,
        categoria_key,
        categoria_classificada,
        unidade_normalizada,
        data_publicacao,
        valor_unitario_estimado,
        percent_rank() over grupo as percentil,
        count(*) over (partition by categoria_key, unidade_normalizada) as itens_comparaveis
    from {{ ref('fato_contratacao_item') }}
    where valor_unitario_estimado is not null
    window grupo as (
        partition by categoria_key, unidade_normalizada order by valor_unitario_estimado
    )
)

select
    item_key,
    numero_controle_pncp,
    numero_item,
    orgao_key,
    categoria_key,
    categoria_classificada,
    unidade_normalizada,
    data_publicacao,
    valor_unitario_estimado,
    round(percentil::numeric, 4) as percentil_preco,
    itens_comparaveis,
    -- o alerta só vale quando a comparação faz sentido:
    -- * categoria classificada (sem NCM, "comparáveis" podem ser uma van e uma caneta);
    -- * amostra mínima (com 2 itens, "o mais caro" não quer dizer nada)
    percentil >= 0.9
    and categoria_classificada
    and itens_comparaveis >= {{ var('min_itens_comparaveis') }} as acima_p90
from ranqueados
