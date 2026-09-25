// Formatação para o usuário brasileiro (pt-BR).
//
// Dinheiro chega da API como TEXTO ("1500.5000"), nunca como número JSON: o backend
// é exato (Decimal). Aqui ele vira número só para EXIBIR, arredondado a centavos.
//
// Datas: toda data com hora é mostrada no horário de Brasília, seja qual for o fuso
// da máquina de quem acessa. Datas SEM hora ("2026-09-01") nunca passam por
// `new Date(...)`: o JavaScript as lê como meia-noite UTC, que em Brasília ainda é o
// dia anterior (31/08 às 21h).

const FUSO = "America/Sao_Paulo";
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});
const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const dataHora = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
  timeZone: FUSO,
});

type Valor = string | number | null | undefined;

function paraNumero(valor: Valor): number | null {
  if (valor === null || valor === undefined || valor === "") return null;
  const n = typeof valor === "number" ? valor : Number(valor);
  return Number.isFinite(n) ? n : null;
}

/** "1500.5000" -> "R$ 1.500,50". Nulo -> `seNulo` (ex.: "Sigiloso" para orçamento sigiloso). */
export function formatarMoeda(valor: Valor, seNulo = "—"): string {
  const n = paraNumero(valor);
  return n === null ? seNulo : moeda.format(n);
}

/** Para KPIs e eixos de gráfico: "148851981.79" -> "R$ 148,9 mi". */
export function formatarMoedaCompacta(valor: Valor): string {
  const n = paraNumero(valor);
  return n === null ? "—" : moedaCompacta.format(n);
}

/** "11000.0000" -> "11.000"; "2.5000" -> "2,5". */
export function formatarNumero(valor: Valor): string {
  const n = paraNumero(valor);
  return n === null ? "—" : numero.format(n);
}

export function formatarInteiro(valor: Valor): string {
  const n = paraNumero(valor);
  return n === null ? "—" : inteiro.format(n);
}

/** "10.00" -> "10,00%" (o backend já manda em pontos percentuais). */
export function formatarPercentual(valor: Valor): string {
  const n = paraNumero(valor);
  if (n === null) return "—";
  return `${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

/** Instante ISO (com fuso) -> "10/03/2025, 23:30", no horário de Brasília. */
export function formatarDataHora(iso: string): string {
  const data = new Date(iso);
  return Number.isNaN(data.getTime()) ? "—" : dataHora.format(data);
}

function partesDaData(iso: string): [number, number, number] | null {
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!partes) return null;
  return [Number(partes[1]), Number(partes[2]), Number(partes[3])];
}

/** Data sem hora "2026-01-10" -> "10/01/2026" (sem passar por fuso). */
export function formatarData(iso: string): string {
  const partes = partesDaData(iso);
  if (!partes) return "—";
  const [ano, mes, dia] = partes;
  return `${String(dia).padStart(2, "0")}/${String(mes).padStart(2, "0")}/${ano}`;
}

/** Primeiro dia do mês "2026-09-01" -> "set/2026". */
export function formatarMes(iso: string): string {
  const partes = partesDaData(iso);
  if (!partes) return "—";
  const [ano, mes] = partes;
  return `${MESES[mes - 1] ?? "?"}/${ano}`;
}

/** "07954480000179" -> "07.954.480/0001-79" (numérico ou alfanumérico). */
export function formatarCnpj(cnpj: string): string {
  if (cnpj.length !== 14) return cnpj;
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
}
