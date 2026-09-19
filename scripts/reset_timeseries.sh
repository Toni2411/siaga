#!/usr/bin/env bash
# Kosongkan data time series, bukan skemanya.
#
# Tiap replay memasang cap waktu virtual yang berakhir "sekarang", jadi
# menjalankan replay dua kali menghasilkan dua salinan riwayat yang saling
# bergeser. Jalankan ini sebelum replay ulang supaya riwayatnya bersih.
set -euo pipefail

# TRUNCATE butuh kunci eksklusif; sesi lain yang menggantung di tengah transaksi
# akan memblokirnya tanpa batas, jadi putuskan dulu sesi lain ke database ini.
docker compose exec -T timescaledb psql -U "${TIMESCALE_USER:-siaga}" -d "${TIMESCALE_DB:-siaga_ts}" -q \
  -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid();" \
  -c "TRUNCATE sensor_reading, operating_state, raw_burst;" >/dev/null
echo "==> time series dikosongkan"
