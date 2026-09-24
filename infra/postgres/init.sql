-- Executado pelo Postgres apenas na PRIMEIRA inicialização do volume
-- (scripts em /docker-entrypoint-initdb.d/). Para reexecutar: make down-volumes && make up.

-- pgvector: tipo `vector` e busca por similaridade, usados no RAG (Etapa 08).
CREATE EXTENSION IF NOT EXISTS vector;
