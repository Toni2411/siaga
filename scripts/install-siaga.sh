#!/usr/bin/env bash
# Pasang app siaga ke site yang sudah hidup.
#
# Kode app sudah ada di image, jadi yang tersisa hanya mendaftarkannya ke site.
# Aman dijalankan berulang: kalau sudah terpasang, dilewati.
set -euo pipefail

SITE="${SITE_NAME:-siaga.localhost}"

if docker compose exec -T backend bench --site "$SITE" list-apps 2>/dev/null | grep -qE '^siaga\s'; then
  echo "==> siaga sudah terpasang di $SITE, dilewati"
  exit 0
fi

echo "==> memasang siaga ke site $SITE"
docker compose exec -T backend bench --site "$SITE" install-app siaga

echo "==> selesai. Buka http://localhost:${HTTP_PORT:-8080}"
