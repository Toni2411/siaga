#!/usr/bin/env bash
# Kembalikan pemantauan ke nol: hapus semua Health Score, kembalikan profil ke
# "Belum terdaftar", dan buang model per unit. Data time series tidak disentuh.
#
# Dipakai sebelum demo, atau setelah mengubah model/ciri supaya seluruh riwayat
# dinilai ulang oleh model yang baru.
set -euo pipefail

SITE="${SITE_NAME:-siaga.localhost}"
MODEL_DIR="${SIAGA_MODEL_DIR:-services/ai/data/models}"

docker compose exec -T backend bench --site "$SITE" execute frappe.db.delete --args '["Health Score"]' >/dev/null
docker compose exec -T backend bench --site "$SITE" execute frappe.db.sql --args '["update `tabAsset Monitoring Profile` set monitoring_status=%s, baseline_started_on=NULL, baseline_completed_on=NULL, model_version=NULL, model_trained_on=NULL, last_score=0, last_score_at=NULL", ["Belum terdaftar"]]' >/dev/null
docker compose exec -T backend bench --site "$SITE" execute frappe.db.commit >/dev/null
rm -f "$MODEL_DIR"/*.joblib 2>/dev/null || true
docker volume ls -q | grep -q "_models$" && docker compose run --rm --no-deps ai sh -c 'rm -f /models/*.joblib' >/dev/null 2>&1 || true
echo "==> pemantauan direset: Health Score kosong, profil Belum terdaftar, model dibuang"
