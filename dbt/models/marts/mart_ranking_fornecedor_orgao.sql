-- Ranking dos fornecedores de cada órgão pelo valor homologado (RANK).
-- GRÃO: órgão x fornecedor. Só itens com vencedor entram.
--
-- RANK dá a mesma posição a empates e PULA as seguintes (1, 1, 3). DENSE_RANK não
-- pularia (1, 1, 2); ROW_NUMBER desempataria arbitrariamente (1, 2, 3).
with vencidos as (
    select
        orgao_key,
        fornecedor_key,
        count(*) as itens_vencidos,
        sum(valor_total_homologado) as valor_total_homologado
    from {{ ref('fato_contratacao_item') }}
    where fornecedor_key is not null
    group by 1, 2
)

select
    orgao_key,
    fornecedor_key,
    itens_vencidos,
    valor_total_homologado,
    rank() over (partition by orgao_key order by valor_total_homologado desc) as ranking,
    -- SUM como janela: o total do órgão aparece em cada linha, sem GROUP BY
    round(
        valor_total_homologado
        / nullif(sum(valor_total_homologado) over (partition by orgao_key), 0) * 100,
        2
    ) as participacao_percentual
from vencidos
