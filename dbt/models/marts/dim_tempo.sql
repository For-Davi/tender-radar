-- Dimensão tempo: 1 linha por dia, gerada pelo próprio Postgres (generate_series).
-- Começa em 2021 (Lei 14.133, que criou o PNCP) e vai até o fim do ano que vem.
-- Ter TODOS os dias (e não só os que têm contratação) permite achar meses "vazios".
with dias as (
    select dia::date as data
    from generate_series(
        date '2021-01-01',
        (date_trunc('year', current_date) + interval '2 years' - interval '1 day')::date,
        interval '1 day'
    ) as dia
)

select
    data,
    extract(year from data)::int as ano,
    extract(quarter from data)::int as trimestre,
    extract(month from data)::int as mes,
    -- nomes fixos em português: to_char('Month') depende do idioma do servidor
    (array[
        'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
        'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'
    ])[extract(month from data)::int] as nome_mes,
    date_trunc('month', data)::date as ano_mes,
    extract(day from data)::int as dia,
    extract(isodow from data)::int as dia_semana,  -- 1 = segunda ... 7 = domingo
    extract(isodow from data) in (6, 7) as fim_de_semana
from dias
