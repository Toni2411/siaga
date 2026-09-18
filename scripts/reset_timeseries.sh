#!/usr/bin/env bash
# Kosongkan data time series, bukan skemanya.
#
# Tiap replay memasang cap waktu virtual yang berakhir "sekarang", jadi
# menjalankan replay dua kali menghasilkan dua salinan riwayat yang saling
# bergeser. Jalankan ini sebelum replay ulang supaya riwayatnya bersih.
set -euo pipefail
docker compose exec -T timescaledb psql -U "${TIMESCALE_USER:-siaga}" -d "${TIMESCALE_DB:-siaga_ts}" \
  -c "TRUNCATE sensor_reading, operating_state, raw_burst;"
echo "==> time series dikosongkan"
