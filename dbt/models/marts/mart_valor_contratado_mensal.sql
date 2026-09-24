-- Valor estimado das contratações por mês, com média móvel de 3 meses.
-- GRÃO: mês (todos os meses entre o primeiro e o último com dados, SEM buracos).
--
-- Por que preencher os meses vazios? A janela "ROWS BETWEEN 2 PRECEDING" conta
-- LINHAS, não meses. Se março não existir como linha, a "média de 3 meses" de abril
-- usaria janeiro, fevereiro e abril: um período de 4 meses chamado de 3.
-- Com a série completa (mês vazio = 0), 3 linhas são sempre 3 meses.
with valores as (
    select
        date_trunc('month', data_publicacao)::date as mes,
        count(distinct numero_controle_pncp) as contratacoes,
        count(*) as itens,
        -- sigilosos somam como desconhecidos (ignorados), não como zero
        coalesce(sum(valor_total_estimado), 0) as valor_total_estimado
    from {{ ref('fato_contratacao_item') }}
    group by 1
),

meses as (
    select distinct ano_mes as mes
    from {{ ref('dim_tempo') }}
    where ano_mes between (select min(mes) from valores) and (select max(mes) from valores)
)

select
    meses.mes,
    coalesce(valores.contratacoes, 0) as contratacoes,
    coalesce(valores.itens, 0) as itens,
    coalesce(valores.valor_total_estimado, 0) as valor_total_estimado,
    round(avg(coalesce(valores.valor_total_estimado, 0)) over janela, 2) as media_movel_3m,
    -- nos 2 primeiros meses a janela tem menos de 3 meses: quem lê precisa saber
    count(*) over janela as meses_na_media
from meses
left join valores
    on valores.mes = meses.mes
window janela as (order by meses.mes rows between 2 preceding and current row)
