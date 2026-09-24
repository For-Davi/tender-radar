-- Fornecedores (quem venceu itens), com o tipo de pessoa traduzido.
select
    id as fornecedor_id,
    documento,
    tipo_pessoa,
    case tipo_pessoa
        when 'PJ' then 'Pessoa jurídica'
        when 'PF' then 'Pessoa física'
        when 'PE' then 'Pessoa estrangeira'
    end as tipo_pessoa_nome,
    nome
from {{ source('silver', 'fornecedor') }}
