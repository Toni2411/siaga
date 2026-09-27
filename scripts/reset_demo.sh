#!/usr/bin/env bash
# Kembalikan seluruh rantai otomasi ke titik awal supaya demo bisa diulang:
# batalkan semua work order otomatis termasuk yang sudah selesai (reservasinya
# ikut lepas, dan jam perbaikannya tidak menumpuk di laporan ketersediaan),
# hapus draft Material Request buatan SIAGA, isi ulang stok part ke jumlah awal,
# reset pemantauan (skor, profil, model), dan kosongkan time series. Replay berikutnya menaruh riwayatnya
# berakhir "sekarang"; kalau data lama dibiarkan, dua riwayat bertumpuk dan
# skornya bergantian antara dua cuplikan yang berbeda. Master data tidak disentuh.
set -euo pipefail

SITE="${SITE_NAME:-siaga.localhost}"

docker compose exec -T backend bench --site "$SITE" execute siaga.demo.reset_automation
bash "$(dirname "$0")/reset_monitoring.sh"
bash "$(dirname "$0")/reset_timeseries.sh"
echo "==> demo direset. Jalankan replay lagi: docker compose --profile replay run --rm edge"
echo "    lalu tutup satu work order: bench execute siaga.demo.close_alarm_work_order"
