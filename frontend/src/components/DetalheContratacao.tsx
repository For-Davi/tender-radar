"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ApiError, type Schemas } from "@/lib/api/client";
import { useContratacao } from "@/lib/api/queries";
import { formatarCnpj, formatarDataHora, formatarMoeda, formatarNumero } from "@/lib/format";

import { Carregando, Erro, Vazio } from "./Estados";

type Detalhe = Schemas["ContratacaoDetalheResponse"];
type Item = Detalhe["itens"][number];

/** Link para a página da contratação no próprio PNCP. */
export function urlPncp(numeroControle: string): string | null {
  const partes = /^(\w{14})-1-(\d{6})\/(\d{4})$/.exec(numeroControle);
  if (!partes) return null;
  const [, cnpj, sequencial, ano] = partes;
  return `https://pncp.gov.br/app/editais/${cnpj}/${ano}/${Number(sequencial)}`;
}

export function DetalheContratacao({ id }: { id: string }) {
  const consulta = useContratacao(id);

  if (consulta.isPending) return <Carregando texto="Carregando contratação…" />;
  if (consulta.isError) {
    if (consulta.error instanceof ApiError && consulta.error.naoEncontrado) {
      return (
        <Vazio>
          Contratação não encontrada.{" "}
          <Link href="/contratacoes" className="text-marca underline">
            Voltar para a lista
          </Link>
        </Vazio>
      );
    }
    return <Erro erro={consulta.error} titulo="Não foi possível carregar a contratação" />;
  }
  return <Conteudo c={consulta.data} />;
}

function Conteudo({ c }: { c: Detalhe }) {
  const pncp = urlPncp(c.numero_controle_pncp);
  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Link href="/contratacoes" className="text-sm text-marca hover:underline">
          ← Contratações
        </Link>
        <h1 className="text-xl font-bold">{c.objeto}</h1>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
          <Campo nome="Órgão">
            {c.orgao.razao_social} ({formatarCnpj(c.orgao.cnpj)})
          </Campo>
          <Campo nome="Número de controle PNCP">{c.numero_controle_pncp}</Campo>
          <Campo nome="Modalidade">{c.modalidade_nome}</Campo>
          <Campo nome="Situação">{c.situacao_nome}</Campo>
          <Campo nome="Publicação">{formatarDataHora(c.data_publicacao)}</Campo>
          <Campo nome="Local">
            {c.municipio}/{c.uf}
          </Campo>
          <Campo nome="Valor total estimado">
            {formatarMoeda(c.valor_total_estimado, "Sigiloso")}
          </Campo>
          {pncp && (
            <Campo nome="Fonte">
              <a href={pncp} target="_blank" rel="noreferrer" className="text-marca underline">
                Ver no PNCP
              </a>
            </Campo>
          )}
        </dl>
      </header>

      <TabelaItens itens={c.itens} />
    </article>
  );
}

function Campo({ nome, children }: { nome: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500">{nome}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}

function TabelaItens({ itens }: { itens: Item[] }) {
  if (itens.length === 0) return <Vazio>Esta contratação não tem itens publicados.</Vazio>;
  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <caption className="p-3 text-left font-semibold">Itens ({itens.length})</caption>
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            <th scope="col" className="px-3 py-2">
              Nº
            </th>
            <th scope="col" className="px-3 py-2">
              Descrição
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Quantidade
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Valor unitário
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Valor total
            </th>
            <th scope="col" className="px-3 py-2">
              Vencedor
            </th>
          </tr>
        </thead>
        <tbody>
          {itens.map((item) => (
            <tr key={item.numero_item} className="border-t border-slate-100 align-top">
              <td className="px-3 py-2">{item.numero_item}</td>
              <td className="max-w-md px-3 py-2">
                {item.descricao}
                <span className="block text-xs text-slate-500">
                  {item.material_ou_servico_nome}
                  {item.ncm_nbs && ` · NCM ${item.ncm_nbs}`}
                </span>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                {formatarNumero(item.quantidade)} {item.unidade_medida}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                {formatarMoeda(item.valor_unitario_estimado, "Sigiloso")}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                {formatarMoeda(item.valor_total_estimado, "Sigiloso")}
              </td>
              <td className="px-3 py-2">
                {item.vencedor ? (
                  <>
                    {item.vencedor.nome}
                    <span className="block text-xs text-slate-500">
                      Homologado: {formatarMoeda(item.valor_unitario_homologado)} / un.
                    </span>
                  </>
                ) : (
                  <span className="text-slate-500">Sem resultado</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
