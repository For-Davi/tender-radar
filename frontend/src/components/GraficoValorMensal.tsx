"use client";

// Valor estimado contratado por mês (barras) e a média móvel de 3 meses (linha).
// O desenho (SVG do Recharts) é escondido do leitor de tela, que lê a tabela
// equivalente logo abaixo: um gráfico sozinho não é acessível.
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Schemas } from "@/lib/api/client";
import { useValorMensal } from "@/lib/api/queries";
import { formatarInteiro, formatarMes, formatarMoeda, formatarMoedaCompacta } from "@/lib/format";

import { Carregando, Erro, Vazio } from "./Estados";

type Mes = Schemas["ValorMensalResponse"];

export function GraficoValorMensal() {
  const consulta = useValorMensal();
  return (
    <figure
      aria-labelledby="titulo-valor-mensal"
      className="min-w-0 rounded border border-slate-200 bg-white p-4"
    >
      <figcaption id="titulo-valor-mensal" className="mb-3 font-semibold">
        Valor contratado por mês
      </figcaption>
      {consulta.isPending ? (
        <Carregando texto="Carregando série mensal…" />
      ) : consulta.isError ? (
        <Erro erro={consulta.error} titulo="Série mensal indisponível" />
      ) : consulta.data.length === 0 ? (
        <Vazio>Ainda não há meses com contratações.</Vazio>
      ) : (
        <Conteudo meses={consulta.data} />
      )}
    </figure>
  );
}

function Conteudo({ meses }: { meses: Mes[] }) {
  // o Recharts precisa de números; os valores exatos continuam na tabela (texto)
  const dados = meses.map((m) => ({
    mes: m.mes,
    valor: Number(m.valor_total_estimado),
    media: Number(m.media_movel_3m),
  }));
  return (
    <>
      <div aria-hidden="true" className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={dados} margin={{ left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="mes" tickFormatter={formatarMes} />
            <YAxis tickFormatter={formatarMoedaCompacta} width={90} />
            <Tooltip
              labelFormatter={(mes) => formatarMes(String(mes))}
              formatter={(valor) => formatarMoeda(Number(valor))}
            />
            <Legend />
            <Bar dataKey="valor" name="Valor estimado" fill="#1d4ed8" isAnimationActive={false} />
            <Line
              dataKey="media"
              name="Média móvel (3 meses)"
              stroke="#b45309"
              strokeWidth={2}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {/* sr-only numa div: uma <table> não aceita largura menor que o conteúdo */}
      <div className="sr-only">
        <table>
          <caption>Valor contratado por mês (dados do gráfico)</caption>
          <thead>
            <tr>
              <th scope="col">Mês</th>
              <th scope="col">Contratações</th>
              <th scope="col">Valor estimado</th>
              <th scope="col">Média móvel de 3 meses</th>
            </tr>
          </thead>
          <tbody>
            {meses.map((m) => (
              <tr key={m.mes}>
                <th scope="row">{formatarMes(m.mes)}</th>
                <td>{formatarInteiro(m.contratacoes)}</td>
                <td>{formatarMoeda(m.valor_total_estimado)}</td>
                <td>
                  {formatarMoeda(m.media_movel_3m)}
                  {/* nos primeiros meses a média tem menos de 3 meses: quem lê precisa saber */}
                  {m.meses_na_media < 3 &&
                    ` (${m.meses_na_media} ${m.meses_na_media === 1 ? "mês" : "meses"})`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
