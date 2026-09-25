import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Navegacao } from "./Navegacao";

describe("Navegacao", () => {
  it("tem os links principais dentro de uma navegação nomeada", () => {
    render(<Navegacao />);

    const nav = screen.getByRole("navigation", { name: "Principal" });
    const links = within(nav)
      .getAllByRole("link")
      .map((link) => [link.textContent, link.getAttribute("href")]);
    expect(links).toEqual([
      ["Radar de Licitações", "/"],
      ["Painel", "/"],
      ["Contratações", "/contratacoes"],
    ]);
  });
});
