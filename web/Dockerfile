# Stage 1: сборка React — на родной платформе сборщика ($BUILDPLATFORM):
# результат (dist/) не зависит от архитектуры, а Node под эмуляцией QEMU
# при сборке arm64 падает (Illegal instruction).
FROM --platform=$BUILDPLATFORM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS builder
ARG APP_VERSION=dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN VITE_APP_VERSION="${APP_VERSION}" npm run build

# Stage 2: nginx раздаёт статику, TLS, проксирует /api в panel-api
FROM nginx:1.30.6-alpine@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951 AS runtime
ARG APP_VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/prg77/tunnelwright-panel-awg" \
      org.opencontainers.image.version="${APP_VERSION}"
COPY --from=builder /app/dist /usr/share/nginx/html
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Режим (HTTPS или HTTP за прокси) и сертификат выбираются при старте — см. tls.sh
COPY --chmod=755 tls.sh /docker-entrypoint.d/40-tunnelwright-tls.sh
EXPOSE 443
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- --no-check-certificate https://127.0.0.1/health >/dev/null 2>&1 \
   || wget -qO- http://127.0.0.1:443/health >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
