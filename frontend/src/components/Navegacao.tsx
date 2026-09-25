import Link from "next/link";

// Server component: só links, sem estado. O <Link> do Next navega sem recarregar a página.
export function Navegacao() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <nav aria-label="Principal" className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-bold text-marca">
          Radar de Licitações
        </Link>
        <ul className="flex gap-4 text-sm">
          <li>
            <Link href="/" className="hover:underline">
              Painel
            </Link>
          </li>
          <li>
            <Link href="/contratacoes" className="hover:underline">
              Contratações
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}
