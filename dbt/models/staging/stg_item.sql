-- Itens das contratações: valores totais calculados, unidade normalizada e o
-- capítulo do NCM (base da categoria).
with itens as (
    select
        id as item_id,
        contratacao_id,
        numero_item,
        descricao,
        material_ou_servico,
        ncm_nbs,
        quantidade,
        unidade_medida,
        {{ normalizar_unidade('unidade_medida') }} as unidade_base,
        valor_unitario_estimado,
        fornecedor_id,
        valor_unitario_homologado
    from {{ source('silver', 'item_contratacao') }}
)

select
    itens.item_id,
    itens.contratacao_id,
    itens.numero_item,
    itens.descricao,
    itens.material_ou_servico,
    itens.ncm_nbs,
    left(itens.ncm_nbs, 2) as ncm_capitulo,
    itens.quantidade,
    itens.unidade_medida,
    -- sinônimo conhecido (seed) ou a própria forma base
    coalesce(sinonimos.unidade, itens.unidade_base) as unidade_normalizada,
    itens.valor_unitario_estimado,
    itens.quantidade * itens.valor_unitario_estimado as valor_total_estimado,
    -- NULL no estimado = orçamento sigiloso (Etapa 03): desconhecido, não zero
    itens.valor_unitario_estimado is null as orcamento_sigiloso,
    itens.fornecedor_id,
    itens.valor_unitario_homologado,
    itens.quantidade * itens.valor_unitario_homologado as valor_total_homologado
from itens
left join {{ ref('unidades_sinonimos') }} as sinonimos
    on sinonimos.variante = itens.unidade_base
