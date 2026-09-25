import type { Metadata } from "next";

import { Navegacao } from "@/components/Navegacao";

import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Radar de Licitações", template: "%s · Radar de Licitações" },
  description: "Contratações públicas do PNCP: busca, detalhes e indicadores de preço.",
};

// Server component: o layout é o mesmo em todas as páginas e não tem estado.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen font-sans">
        {/* link "pular para o conteúdo": o 1º Tab do teclado leva direto ao principal */}
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-white focus:p-2"
        >
          Pular para o conteúdo
        </a>
        <Navegacao />
        <main id="conteudo" className="mx-auto max-w-6xl px-4 py-6">
          <Providers>{children}</Providers>
        </main>
      </body>
    </html>
  );
}
