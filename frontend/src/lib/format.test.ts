import { describe, expect, it } from "vitest";

import {
  formatarCnpj,
  formatarData,
  formatarDataHora,
  formatarInteiro,
  formatarMes,
  formatarMoeda,
  formatarMoedaCompacta,
  formatarNumero,
  formatarPercentual,
} from "./format";

// O Intl usa espaço não separável (U+00A0) entre "R$" e o número: normalizamos para
// comparar com texto legível.
const semNbsp = (texto: string) => texto.replace(/ /g, " ");

describe("formatarMoeda", () => {
  it.each([
    ["1500.5000", "R$ 1.500,50"],
    ["0.3333", "R$ 0,33"],
    ["148851981.78880000", "R$ 148.851.981,79"],
    ["0", "R$ 0,00"],
    [1234.5, "R$ 1.234,50"],
  ])("%s -> %s", (entrada, esperado) => {
    expect(semNbsp(formatarMoeda(entrada))).toBe(esperado);
  });

  it("nulo usa o texto informado (ex.: orçamento sigiloso)", () => {
    expect(formatarMoeda(null, "Sigiloso")).toBe("Sigiloso");
  });

  it("nulo, vazio ou inválido vira travessão por padrão", () => {
    expect(formatarMoeda(null)).toBe("—");
    expect(formatarMoeda(undefined)).toBe("—");
    expect(formatarMoeda("")).toBe("—");
    expect(formatarMoeda("abc")).toBe("—");
  });
});

describe("formatarMoedaCompacta", () => {
  it("abrevia milhões", () => {
    expect(semNbsp(formatarMoedaCompacta("148851981.79"))).toBe("R$ 148,9 mi");
  });

  it("nulo vira travessão", () => {
    expect(formatarMoedaCompacta(null)).toBe("—");
  });
});

describe("números", () => {
  it.each([
    ["11000.0000", "11.000"],
    ["2.5000", "2,5"],
    ["0.0345", "0,0345"],
  ])("formatarNumero %s -> %s", (entrada, esperado) => {
    expect(formatarNumero(entrada)).toBe(esperado);
  });

  it("formatarInteiro usa separador de milhar", () => {
    expect(formatarInteiro(1010)).toBe("1.010");
    expect(formatarInteiro(null)).toBe("—");
  });

  it("nulo vira travessão", () => {
    expect(formatarNumero(null)).toBe("—");
  });

  it.each([
    ["10.00", "10,00%"],
    ["-2.5", "-2,50%"],
    ["97.59", "97,59%"],
  ])("formatarPercentual %s -> %s", (entrada, esperado) => {
    expect(formatarPercentual(entrada)).toBe(esperado);
  });

  it("percentual nulo vira travessão", () => {
    expect(formatarPercentual(null)).toBe("—");
  });
});

describe("datas", () => {
  it("instante UTC é mostrado no horário de Brasília", () => {
    // 02:30 UTC de 11/03 = 23:30 de 10/03 em Brasília (UTC-3)
    expect(formatarDataHora("2025-03-11T02:30:00Z")).toBe("10/03/2025, 23:30");
  });

  it("instante inválido vira travessão", () => {
    expect(formatarDataHora("ontem")).toBe("—");
  });

  it("data sem hora não volta um dia (não passa por UTC)", () => {
    // os testes rodam com TZ=America/Sao_Paulo: new Date("2026-01-10") daria 09/01
    expect(formatarData("2026-01-10")).toBe("10/01/2026");
  });

  it.each([
    ["2026-09-01", "set/2026"],
    ["2026-01-01", "jan/2026"],
    ["2025-12-01", "dez/2025"],
  ])("formatarMes %s -> %s", (entrada, esperado) => {
    expect(formatarMes(entrada)).toBe(esperado);
  });

  it("data em formato inesperado vira travessão", () => {
    expect(formatarData("10/01/2026")).toBe("—");
    expect(formatarMes("2026-09")).toBe("—");
  });
});

describe("formatarCnpj", () => {
  it("aplica a máscara", () => {
    expect(formatarCnpj("07954480000179")).toBe("07.954.480/0001-79");
    expect(formatarCnpj("12ABC34501DE35")).toBe("12.ABC.345/01DE-35");
  });

  it("documento que não é CNPJ fica como veio", () => {
    expect(formatarCnpj("12345678901")).toBe("12345678901");
  });
});
