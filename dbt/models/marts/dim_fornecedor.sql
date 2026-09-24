-- Dimensão fornecedor: quem vende (venceu ao menos um item).
select
    md5(documento) as fornecedor_key,
    documento,
    tipo_pessoa,
    tipo_pessoa_nome,
    nome
from {{ ref('stg_fornecedor') }}
