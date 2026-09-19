# Satu image untuk semua service Python SIAGA (edge, gateway, nanti AI).
# Perintah yang dijalankan dipilih di docker-compose.yml.

FROM python:3.11-slim

WORKDIR /app
COPY services/edge /app/edge
COPY services/gateway /app/gateway
COPY services/ai /app/ai
RUN pip install --no-cache-dir /app/edge /app/gateway /app/ai

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "siaga_gateway"]
