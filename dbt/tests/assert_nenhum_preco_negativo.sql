-- Nenhum preço, quantidade ou total negativo na fato (a silver já valida; isto
-- protege contra um cálculo errado na própria gold, como um sinal trocado).
select item_key, quantidade, valor_unitario_estimado, valor_unitario_homologado
from {{ ref('fato_contratacao_item') }}
where quantidade <= 0
    or valor_unitario_estimado < 0
    or valor_total_estimado < 0
    or valor_unitario_homologado < 0
    or valor_total_homologado < 0
