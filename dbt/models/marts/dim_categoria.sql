-- Dimensão categoria: tipo (material/serviço) + capítulo do NCM.
-- O PNCP manda "itemCategoriaNome" sempre como "Não se aplica"; o NCM (quando vem) é a
-- melhor classificação disponível. Sem NCM, a categoria é "sem classificação".
with combinacoes as (
    select distinct material_ou_servico, ncm_capitulo
    from {{ ref('stg_item') }}
)

select
    {{ categoria_key('c.material_ou_servico', 'c.ncm_capitulo') }} as categoria_key,
    c.material_ou_servico,
    case c.material_ou_servico when 'M' then 'Material' else 'Serviço' end as tipo,
    c.ncm_capitulo,
    case
        when c.ncm_capitulo is null
            then case c.material_ou_servico
                when 'M' then 'Material sem classificação'
                else 'Serviço sem classificação'
            end
        -- capítulo fora do seed (ex.: código NBS de serviço): mostra só o número
        else c.ncm_capitulo || ' - ' || coalesce(n.descricao, 'Capítulo ' || c.ncm_capitulo)
    end as categoria_nome
from combinacoes as c
left join {{ ref('ncm_capitulos') }} as n
    on n.capitulo = c.ncm_capitulo
