-- Fato central do star schema. GRÃO: 1 linha por item de uma contratação.
--
-- Chaves estrangeiras para as dimensões (órgão, fornecedor, categoria, tempo) e
-- medidas numéricas (quantidade e valores). Atributos da contratação que não merecem
-- dimensão própria (modalidade, UF, número de controle) ficam aqui como
-- "dimensões degeneradas".
select
    md5(c.numero_controle_pncp || '|' || i.numero_item) as item_key,
    c.numero_controle_pncp,
    i.numero_item,

    -- chaves das dimensões
    md5(o.cnpj) as orgao_key,
    -- nulo quando o item ainda não tem vencedor (a maioria, em contratações recentes)
    case when f.documento is not null then md5(f.documento) end as fornecedor_key,
    {{ categoria_key('i.material_ou_servico', 'i.ncm_capitulo') }} as categoria_key,
    c.data_publicacao_local as data_publicacao,

    -- dimensões degeneradas
    c.modalidade,
    c.modalidade_nome,
    c.uf,
    c.municipio,
    i.material_ou_servico,
    -- categoria de verdade (com NCM) ou "sem classificação" (a maioria dos itens)
    i.ncm_capitulo is not null as categoria_classificada,
    i.unidade_normalizada,
    i.orcamento_sigiloso,

    -- medidas
    i.quantidade,
    i.valor_unitario_estimado,
    i.valor_total_estimado,
    i.valor_unitario_homologado,
    i.valor_total_homologado,
    -- desconto obtido na disputa: quanto o preço final ficou abaixo do estimado
    case
        when i.valor_unitario_estimado > 0 and i.valor_unitario_homologado is not null
            then round(
                (1 - i.valor_unitario_homologado / i.valor_unitario_estimado) * 100, 2
            )
    end as desconto_percentual
from {{ ref('stg_item') }} as i
inner join {{ ref('stg_contratacao') }} as c
    on c.contratacao_id = i.contratacao_id
inner join {{ ref('stg_orgao') }} as o
    on o.orgao_id = c.orgao_id
left join {{ ref('stg_fornecedor') }} as f
    on f.fornecedor_id = i.fornecedor_id
