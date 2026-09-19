#!/usr/bin/env bash
# Tes app Frappe di dalam container backend yang sedang jalan.
#
# Tes berjalan di transaksi yang digulung balik, jadi aman di site demo:
# data uji berawalan UJI- tidak tersisa. --skip-test-records mencegah runner
# membuat data uji bawaan ERPNext (perusahaan _Test Company dan kawan-kawan).
set -euo pipefail
SITE="${SITE_NAME:-siaga.localhost}"
docker compose exec -T backend bench --site "$SITE" set-config allow_tests true >/dev/null
docker compose exec -T backend bench --site "$SITE" run-tests --app siaga --skip-test-records "$@"
