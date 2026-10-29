# Tunnelwright Panel AWG node-agent: управляет wg-easy, tc-лимитами и блокировкой торрентов на ноде.
# Запускается в сетевом namespace контейнера wg-easy (network_mode: service:wg-easy).
FROM python:3.14.10-slim@sha256:3cabfd7d7aaf394e6040e79fa1eec6ca1c52b74ed9188650472695d9a9326999
ARG APP_VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/prg77/tunnelwright-panel-awg" \
      org.opencontainers.image.version="${APP_VERSION}"
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 iptables \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV APP_VERSION=${APP_VERSION} PYTHONUNBUFFERED=1
EXPOSE 8710
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8710", "--no-access-log"]
