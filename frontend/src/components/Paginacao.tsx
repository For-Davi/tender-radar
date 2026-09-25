import { formatarInteiro } from "@/lib/format";

interface Props {
  pagina: number;
  totalPaginas: number;
  total: number;
  onMudar: (pagina: number) => void;
}

/** "Anterior / Página X de Y / Próxima". Some quando não há resultados. */
export function Paginacao({ pagina, totalPaginas, total, onMudar }: Props) {
  if (total === 0) return null;
  const naPrimeira = pagina <= 1;
  // página além da última (ex.: URL antiga): "próxima" fica desabilitada
  const naUltima = pagina >= totalPaginas;
  return (
    <nav aria-label="Paginação" className="mt-4 flex items-center justify-between gap-4 text-sm">
      <button
        type="button"
        onClick={() => onMudar(pagina - 1)}
        disabled={naPrimeira}
        className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
      >
        Anterior
      </button>
      <p aria-live="polite">
        Página {formatarInteiro(pagina)} de {formatarInteiro(totalPaginas)} ·{" "}
        {formatarInteiro(total)} resultados
      </p>
      <button
        type="button"
        onClick={() => onMudar(pagina + 1)}
        disabled={naUltima}
        className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-40"
      >
        Próxima
      </button>
    </nav>
  );
}
