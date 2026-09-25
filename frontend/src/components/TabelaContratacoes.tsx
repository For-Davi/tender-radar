import Link from "next/link";

import type { Schemas } from "@/lib/api/client";
import { formatarDataHora, formatarMoeda } from "@/lib/format";

type Contratacao = Schemas["ContratacaoResponse"];

export function TabelaContratacoes({
  contratacoes,
  atualizando = false,
}: {
  contratacoes: Contratacao[];
  atualizando?: boolean;
}) {
  return (
    // overflow: em tela estreita a tabela rola na horizontal em vez de quebrar o layout
    <div className="overflow-x-auto rounded border border-slate-200 bg-white">
      <table aria-busy={atualizando} className="w-full text-left text-sm">
        <caption className="sr-only">Contratações encontradas</caption>
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            <th scope="col" className="px-3 py-2">
              Publicação
            </th>
            <th scope="col" className="px-3 py-2">
              Objeto
            </th>
            <th scope="col" className="px-3 py-2">
              Órgão
            </th>
            <th scope="col" className="px-3 py-2">
              Modalidade
            </th>
            <th scope="col" className="px-3 py-2">
              Local
            </th>
            <th scope="col" className="px-3 py-2 text-right">
              Valor estimado
            </th>
          </tr>
        </thead>
        <tbody className={atualizando ? "opacity-60" : undefined}>
          {contratacoes.map((c) => (
            <tr key={c.id} className="border-t border-slate-100 align-top">
              <td className="whitespace-nowrap px-3 py-2">{formatarDataHora(c.data_publicacao)}</td>
              <td className="max-w-md px-3 py-2">
                <Link
                  href={`/contratacoes/${c.id}`}
                  className="line-clamp-2 text-marca hover:underline"
                >
                  {c.objeto}
                </Link>
              </td>
              <td className="px-3 py-2">{c.orgao.razao_social}</td>
              <td className="px-3 py-2">{c.modalidade_nome}</td>
              <td className="whitespace-nowrap px-3 py-2">
                {c.municipio}/{c.uf}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                {formatarMoeda(c.valor_total_estimado, "Sigiloso")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
