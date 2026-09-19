#!/usr/bin/env bash
# Kembalikan seluruh rantai otomasi ke titik awal supaya demo bisa diulang:
# batalkan work order otomatis yang masih terbuka (reservasinya ikut lepas),
# hapus draft Material Request buatan SIAGA, lalu reset pemantauan (skor,
# profil, model). Data time series dan master data tidak disentuh.
set -euo pipefail

SITE="${SITE_NAME:-siaga.localhost}"

docker compose exec -T backend bench --site "$SITE" execute siaga.demo.reset_automation
bash "$(dirname "$0")/reset_monitoring.sh"
echo "==> demo direset. AI service akan menilai ulang dalam satu siklus."
