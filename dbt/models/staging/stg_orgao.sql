-- Órgãos públicos, com os códigos de esfera e poder traduzidos para nomes.
select
    id as orgao_id,
    cnpj,
    razao_social,
    esfera,
    case esfera
        when 'F' then 'Federal'
        when 'E' then 'Estadual'
        when 'M' then 'Municipal'
        when 'D' then 'Distrital'
        when 'N' then 'Não se aplica'
    end as esfera_nome,
    poder,
    case poder
        when 'E' then 'Executivo'
        when 'L' then 'Legislativo'
        when 'J' then 'Judiciário'
        when 'N' then 'Não se aplica'
    end as poder_nome
from {{ source('silver', 'orgao') }}
