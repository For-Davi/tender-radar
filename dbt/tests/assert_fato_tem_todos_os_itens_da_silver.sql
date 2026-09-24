-- A fato tem exatamente os itens da silver: nenhum perdido por um INNER JOIN com
-- dimensão faltando, nenhum duplicado por um join que multiplica linhas.
with silver as (
    select count(*) as itens from {{ source('silver', 'item_contratacao') }}
),

fato as (
    select count(*) as itens from {{ ref('fato_contratacao_item') }}
)

select silver.itens as itens_silver, fato.itens as itens_fato
from silver cross join fato
where silver.itens <> fato.itens
