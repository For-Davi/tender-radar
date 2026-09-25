# Imagem do frontend (Next.js "standalone").

# ---------- Stage 1: deps — instala exatamente o package-lock ----------
FROM node:24-alpine AS deps
WORKDIR /app
# só os arquivos de dependência: enquanto não mudarem, esta camada vem do cache
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---------- Stage 2: builder — gera .next/standalone ----------
FROM node:24-alpine AS builder
WORKDIR /app
# não mandar telemetria anônima para a Vercel (mesma decisão do dbt, ADR 0005)
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_*: o valor é COPIADO para o JavaScript do navegador durante o build.
# É o endereço da API visto pelo NAVEGADOR (não o "api:8000" da rede do Compose).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------- Stage 3: runtime — só o servidor e os arquivos estáticos ----------
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
# o standalone não inclui public/ nem .next/static: copiados à parte
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
# "node" é o usuário sem privilégios que a imagem oficial já traz
USER node
EXPOSE 3000
CMD ["node", "server.js"]
