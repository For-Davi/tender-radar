// Servidor MSW para o Node (os testes rodam no Node, com jsdom): intercepta o fetch.
import { setupServer } from "msw/node";

import { handlers } from "./handlers";

export const server = setupServer(...handlers);
