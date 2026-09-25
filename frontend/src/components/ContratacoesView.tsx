"use client";

// Tela de busca de contratações. Recebe os filtros e um callback, em vez de ler a URL:
// quem liga isso à URL é a página (src/app/contratacoes). Assim este componente é
// testado com um estado simples, sem simular o roteador do Next.
import { useContratacoes } from "@/lib/api/queries";
import {
  ORDENACOES,
  alterarFiltros,
  filtrosParaUrl,
  temFiltroAtivo,
  type Filtros,
  type Ordenacao,
} from "@/lib/filtros";

import { Carregando, Erro, Vazio } from "./Estados";
import { FiltrosContratacoes } from "./FiltrosContratacoes";
import { Paginacao } from "./Paginacao";
import { TabelaContratacoes } from "./TabelaContratacoes";

interface Props {
  filtros: Filtros;
  onFiltrosChange: (filtros: Filtros) => void;
}

export function ContratacoesView({ filtros, onFiltrosChange }: Props) {
  const consulta = useContratacoes(filtros);
  const mudar = (mudanca: Partial<Filtros>) => onFiltrosChange(alterarFiltros(filtros, mudanca));

  return (
    <section aria-labelledby="titulo-contratacoes" className="flex flex-col gap-4">
      <h1 id="titulo-contratacoes" className="text-2xl font-bold">
        Contratações
      </h1>

      {/* key: se os filtros mudarem por fora (botão voltar), o formulário recomeça com eles */}
      <FiltrosContratacoes key={filtrosParaUrl(filtros)} filtros={filtros} onAplicar={mudar} />

      <label className="flex items-center gap-2 self-end text-sm">
        Ordenar por
        <select
          value={filtros.ordenar}
          onChange={(e) => mudar({ ordenar: e.target.value as Ordenacao })}
          className="rounded border border-slate-300 bg-white px-2 py-1"
        >
          {ORDENACOES.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.rotulo}
            </option>
          ))}
        </select>
      </label>

      <Resultado consulta={consulta} filtros={filtros} onPagina={(pagina) => mudar({ pagina })} />
    </section>
  );
}

function Resultado({
  consulta,
  filtros,
  onPagina,
}: {
  consulta: ReturnType<typeof useContratacoes>;
  filtros: Filtros;
  onPagina: (pagina: number) => void;
}) {
  if (consulta.isPending) return <Carregando texto="Carregando contratações…" />;
  if (consulta.isError)
    return <Erro erro={consulta.error} titulo="Não foi possível buscar as contratações" />;

  const { itens, total, pagina, total_paginas } = consulta.data;
  if (total === 0) {
    return (
      <Vazio>
        {temFiltroAtivo(filtros)
          ? "Nenhuma contratação para estes filtros."
          : "Ainda não há contratações. Rode a ingestão e o pipeline (make pipeline)."}
      </Vazio>
    );
  }
  return (
    <>
      {itens.length === 0 ? (
        <Vazio>Esta página não existe mais. Volte para a página 1.</Vazio>
      ) : (
        // enquanto a próxima página chega, a atual continua na tela, esmaecida
        <TabelaContratacoes contratacoes={itens} atualizando={consulta.isPlaceholderData} />
      )}
      <Paginacao pagina={pagina} totalPaginas={total_paginas} total={total} onMudar={onPagina} />
    </>
  );
}
