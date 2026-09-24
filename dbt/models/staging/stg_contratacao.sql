-- Contratações, com o nome da modalidade e a data de publicação no dia de Brasília.
select
    id as contratacao_id,
    numero_controle_pncp,
    orgao_id,
    ano,
    sequencial,
    modalidade,
    case modalidade
        when 1 then 'Leilão eletrônico'
        when 2 then 'Diálogo competitivo'
        when 3 then 'Concurso'
        when 4 then 'Concorrência eletrônica'
        when 5 then 'Concorrência presencial'
        when 6 then 'Pregão eletrônico'
        when 7 then 'Pregão presencial'
        when 8 then 'Dispensa de licitação'
        when 9 then 'Inexigibilidade'
        when 10 then 'Manifestação de interesse'
        when 11 then 'Pré-qualificação'
        when 12 then 'Credenciamento'
        when 13 then 'Leilão presencial'
    end as modalidade_nome,
    situacao,
    objeto,
    valor_total_estimado,
    data_publicacao,
    -- a silver guarda o instante em UTC; o "dia" da publicação é o dia em Brasília
    -- (publicado às 22h de 31/03 em Brasília é 01h de 01/04 em UTC: mês errado!)
    (data_publicacao at time zone 'America/Sao_Paulo')::date as data_publicacao_local,
    uf,
    municipio
from {{ source('silver', 'contratacao') }}
