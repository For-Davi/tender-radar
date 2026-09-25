import type { Metadata } from "next";

import { DetalheContratacao } from "@/components/DetalheContratacao";

export const metadata: Metadata = { title: "Contratação" };

// No Next 16, `params` é uma Promise: a página (server component) espera o valor e
// passa o id para o componente client, que busca os dados.
export default async function Page({ params }: PageProps<"/contratacoes/[id]">) {
  const { id } = await params;
  return <DetalheContratacao id={id} />;
}
