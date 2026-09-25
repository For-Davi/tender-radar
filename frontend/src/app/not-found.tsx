import Link from "next/link";

// Página para rotas que não existem (o padrão do Next é em inglês).
export default function NotFound() {
  return (
    <section className="flex flex-col items-start gap-3 py-10">
      <h1 className="text-2xl font-bold">Página não encontrada</h1>
      <p className="text-slate-600">O endereço acessado não existe no Radar de Licitações.</p>
      <Link href="/" className="text-marca underline">
        Ir para o painel
      </Link>
    </section>
  );
}
