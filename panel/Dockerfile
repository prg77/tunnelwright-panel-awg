# Tunnelwright Panel AWG panel-api: бэкенд панели (вход, клиенты, лимиты, трафик, Telegram, журнал, настройки)
FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999
ARG APP_VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/prg77/tunnelwright-panel-awg" \
      org.opencontainers.image.version="${APP_VERSION}"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# исходники node-agent — для сборки агента на удалённой ноде, если образ из GHCR недоступен
COPY --from=node Dockerfile requirements.txt ./node_bundle/
COPY --from=node app ./node_bundle/app
ENV APP_VERSION=${APP_VERSION} PYTHONUNBUFFERED=1
EXPOSE 8700
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8700", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
