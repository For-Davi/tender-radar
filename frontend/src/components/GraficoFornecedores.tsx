"use client";

// Top fornecedores pelo valor homologado. O mart do dbt ranqueia POR ÓRGÃO; aqui os
// valores de cada fornecedor são somados entre os órgãos para um ranking geral.
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Schemas } from "@/lib/api/client";
import { useRankingFornecedores } from "@/lib/api/queries";
import { formatarInteiro, formatarMoeda, formatarMoedaCompacta } from "@/lib/format";

import { Carregando, Erro, Vazio } from "./Estados";

type Linha = Schemas["RankingFornecedorResponse"];

export interface FornecedorTotal {
  documento: string;
  nome: string;
  valor: number;
  itens: number;
  orgaos: number;
}

/** Soma por fornecedor (entre órgãos) e devolve os `limite` maiores, do maior ao menor. */
export function agregarFornecedores(linhas: Linha[], limite = 10): FornecedorTotal[] {
  const porDocumento = new Map<string, FornecedorTotal>();
  for (const linha of linhas) {
    const atual = porDocumento.get(linha.fornecedor_documento) ?? {
      documento: linha.fornecedor_documento,
      nome: linha.fornecedor_nome,
      valor: 0,
      itens: 0,
      orgaos: 0,
    };
    atual.valor += Number(linha.valor_total_homologado);
    atual.itens += linha.itens_vencidos;
    atual.orgaos += 1; // o mart tem uma linha por órgão x fornecedor
    porDocumento.set(linha.fornecedor_documento, atual);
  }
  return [...porDocumento.values()]
    .sort((a, b) => b.valor - a.valor || a.nome.localeCompare(b.nome, "pt-BR"))
    .slice(0, limite);
}

export function GraficoFornecedores() {
  const consulta = useRankingFornecedores();
  return (
    <figure
      aria-labelledby="titulo-fornecedores"
      className="rounded border border-slate-200 bg-white p-4"
    >
      <figcaption id="titulo-fornecedores" className="mb-3 font-semibold">
        Top fornecedores por valor homologado
      </figcaption>
      {consulta.isPending ? (
        <Carregando texto="Carregando fornecedores…" />
      ) : consulta.isError ? (
        <Erro erro={consulta.error} titulo="Ranking indisponível" />
      ) : consulta.data.length === 0 ? (
        <Vazio>Nenhum item com vencedor homologado ainda.</Vazio>
      ) : (
        <Conteudo fornecedores={agregarFornecedores(consulta.data)} />
      )}
    </figure>
  );
}

function Conteudo({ fornecedores }: { fornecedores: FornecedorTotal[] }) {
  return (
    <>
      <div aria-hidden="true" style={{ height: 40 + fornecedores.length * 36 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={fornecedores} layout="vertical" margin={{ left: 16, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tickFormatter={formatarMoedaCompacta} />
            <YAxis type="category" dataKey="nome" width={200} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(valor) => formatarMoeda(Number(valor))} />
            <Bar dataKey="valor" name="Valor homologado" fill="#1d4ed8" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Top fornecedores por valor homologado (dados do gráfico)</caption>
        <thead>
          <tr>
            <th scope="col">Fornecedor</th>
            <th scope="col">Valor homologado</th>
            <th scope="col">Itens vencidos</th>
            <th scope="col">Órgãos</th>
          </tr>
        </thead>
        <tbody>
          {fornecedores.map((f) => (
            <tr key={f.documento}>
              <th scope="row">{f.nome}</th>
              <td>{formatarMoeda(f.valor)}</td>
              <td>{formatarInteiro(f.itens)}</td>
              <td>{formatarInteiro(f.orgaos)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
