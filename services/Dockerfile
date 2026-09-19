# Satu image untuk semua service Python SIAGA (edge, gateway, nanti AI).
# Perintah yang dijalankan dipilih di docker-compose.yml.

FROM python:3.11-slim

# bsdtar membuka arsip rar dataset IMS tanpa unrar.
RUN apt-get update && apt-get install -y --no-install-recommends libarchive-tools     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/edge /app/edge
COPY services/gateway /app/gateway
COPY services/ai /app/ai
COPY scripts/prepare_dataset.py /app/scripts/prepare_dataset.py
RUN pip install --no-cache-dir /app/edge /app/gateway /app/ai pandas py7zr

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "siaga_gateway"]
