"use client";

import { GraficoFornecedores } from "./GraficoFornecedores";
import { GraficoValorMensal } from "./GraficoValorMensal";
import { Kpis } from "./Kpis";

export function Dashboard() {
  return (
    <section aria-labelledby="titulo-painel" className="flex flex-col gap-6">
      <div>
        <h1 id="titulo-painel" className="text-2xl font-bold">
          Painel
        </h1>
        <p className="text-sm text-slate-600">
          Contratações públicas publicadas no PNCP. As métricas são atualizadas a cada{" "}
          <code>make dbt</code>.
        </p>
      </div>
      <Kpis />
      <div className="grid gap-6 lg:grid-cols-2">
        <GraficoValorMensal />
        <GraficoFornecedores />
      </div>
    </section>
  );
}
