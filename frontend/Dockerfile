# Local full-stack testing only (local/compose.yaml): the static export in API mode, served the way
# Firebase Hosting serves it, with /api/** passed to the API container (scripts/serve-static.mjs).
# The cloud uses Firebase Hosting instead (infra/scripts/deploy_frontend.sh).
FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build:http

FROM node:24-slim
WORKDIR /app
COPY --from=build /app/out-http ./out-http
COPY scripts/serve-static.mjs ./scripts/serve-static.mjs
ENV STATIC_ROOT=out-http PORT=3080 NODE_ENV=production
USER node
EXPOSE 3080
CMD ["node", "scripts/serve-static.mjs"]
