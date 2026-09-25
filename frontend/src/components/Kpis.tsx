"use client";

// Os 4 números do topo do painel. Cada um vem de uma consulta própria: se a gold
// (métricas) estiver indisponível, os KPIs da silver continuam aparecendo.
import type { UseQueryResult } from "@tanstack/react-query";

import {
  useOrgaos,
  useTotalAlertas,
  useTotalContratacoes,
  useValorMensal,
} from "@/lib/api/queries";
import { formatarInteiro, formatarMoedaCompacta } from "@/lib/format";

import { mensagemDeErro } from "./Estados";

function Kpi<T>({
  titulo,
  consulta,
  formatar,
  dica,
}: {
  titulo: string;
  consulta: UseQueryResult<T>;
  formatar: (valor: T) => string;
  dica?: string;
}) {
  let valor: string;
  if (consulta.isPending) valor = "…";
  else if (consulta.isError) valor = "Indisponível";
  else valor = formatar(consulta.data);
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <dt className="text-sm text-slate-600">{titulo}</dt>
      <dd aria-busy={consulta.isPending} className="mt-1 text-2xl font-bold tabular-nums">
        {valor}
      </dd>
      {consulta.isError ? (
        <dd className="mt-1 text-xs text-alerta">{mensagemDeErro(consulta.error)}</dd>
      ) : (
        dica && <dd className="mt-1 text-xs text-slate-500">{dica}</dd>
      )}
    </div>
  );
}

export function Kpis() {
  const contratacoes = useTotalContratacoes();
  const orgaos = useOrgaos();
  const valorMensal = useValorMensal();
  const alertas = useTotalAlertas();

  return (
    <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <Kpi titulo="Contratações" consulta={contratacoes} formatar={formatarInteiro} />
      <Kpi
        titulo="Valor estimado total"
        consulta={valorMensal}
        // soma da série mensal; valores exatos vêm como texto, a soma é só para exibir
        formatar={(meses) =>
          formatarMoedaCompacta(meses.reduce((soma, m) => soma + Number(m.valor_total_estimado), 0))
        }
        dica="Soma de todos os meses"
      />
      <Kpi titulo="Órgãos" consulta={orgaos} formatar={(pagina) => formatarInteiro(pagina.total)} />
      <Kpi
        titulo="Preços acima do p90"
        consulta={alertas}
        formatar={formatarInteiro}
        dica="Itens mais caros que 90% dos comparáveis"
      />
    </dl>
  );
}
