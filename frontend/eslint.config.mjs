// ESLint (flat config): regras do Next (React, hooks, acessibilidade, Core Web Vitals)
// + regras de TypeScript. O eslint-config-prettier vem por último e DESLIGA as regras de
// estilo que brigariam com o Prettier: o ESLint procura bugs, o Prettier formata.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettier,
  {
    rules: {
      // variável não usada é quase sempre um erro esquecido; "_nome" marca de propósito
      "@typescript-eslint/no-unused-vars": [
        "error",
        // ignoreRestSiblings: `const { a, ...resto } = obj` para TIRAR `a` é intencional
        { argsIgnorePattern: "^_", ignoreRestSiblings: true },
      ],
      // `any` desliga o compilador; no projeto, só com justificativa (eslint-disable + motivo)
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "next-env.d.ts",
    // gerado a partir do OpenAPI do backend: não se edita à mão
    "src/lib/api/schema.d.ts",
  ]),
]);

export default eslintConfig;
