import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Paginacao } from "./Paginacao";

describe("Paginacao", () => {
  it("mostra a posição e o total em pt-BR", () => {
    render(<Paginacao pagina={2} totalPaginas={57} total={1140} onMudar={() => {}} />);

    expect(screen.getByText("Página 2 de 57 · 1.140 resultados")).toBeInTheDocument();
  });

  it("na primeira página, 'Anterior' fica desabilitado", () => {
    render(<Paginacao pagina={1} totalPaginas={3} total={50} onMudar={() => {}} />);

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Próxima" })).toBeEnabled();
  });

  it("na última página, 'Próxima' fica desabilitado", () => {
    render(<Paginacao pagina={3} totalPaginas={3} total={50} onMudar={() => {}} />);

    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeEnabled();
  });

  it("os botões pedem a página vizinha", async () => {
    const onMudar = vi.fn();
    render(<Paginacao pagina={2} totalPaginas={3} total={50} onMudar={onMudar} />);

    await userEvent.click(screen.getByRole("button", { name: "Próxima" }));
    await userEvent.click(screen.getByRole("button", { name: "Anterior" }));

    expect(onMudar.mock.calls).toEqual([[3], [1]]);
  });

  it("sem resultados, não renderiza nada", () => {
    const { container } = render(
      <Paginacao pagina={1} totalPaginas={0} total={0} onMudar={() => {}} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
