-- Dimensão órgão: quem compra.
-- Chave substituta = md5 da chave natural (CNPJ): estável entre rebuilds e independente
-- do id numérico da silver.
select
    md5(cnpj) as orgao_key,
    cnpj,
    razao_social,
    esfera,
    esfera_nome,
    poder,
    poder_nome
from {{ ref('stg_orgao') }}
