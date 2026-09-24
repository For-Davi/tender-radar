-- PERCENT_RANK sempre fica entre 0 e 1; fora disso, a fórmula foi trocada.
select item_key, percentil_preco
from {{ ref('mart_percentil_preco_item') }}
where percentil_preco < 0 or percentil_preco > 1
