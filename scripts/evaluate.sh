#!/usr/bin/env bash
# Hitung ulang angka di README dari cache dataset, tanpa Docker dan tanpa ERPNext.
#
# Ini uji yang paling menenangkan sebelum mempresentasikan proyek: lead time
# dan alarm palsu lahir dari ekstraksi ciri dan model yang sama dengan sistem
# hidup, dijalankan langsung dari berkas dataset.
#
#   bash scripts/evaluate.sh          # kedua dataset
#   bash scripts/evaluate.sh 2        # hanya set 2
#   bash scripts/evaluate.sh 1        # hanya set 1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$ROOT/data/cache"

# Python dari venv proyek; kalau belum ada, pakai python di PATH.
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python"

run() {
	local set_no="$1" file="$2"
	shift 2
	if [ ! -f "$file" ]; then
		echo "==> dataset set $set_no belum ada di $file"
		echo "    siapkan dulu: docker compose --profile replay run --rm prepare --set $set_no"
		return
	fi
	echo
	echo "===== IMS set $set_no ====="
	(cd "$ROOT/services/ai" && "$PY" -m siaga_ai.evaluate --cache "$file" --baseline-days 3 "$@")
}

case "${1:-all}" in
	2) run 2 "$CACHE/ims_2nd_test_3200hz.npz" --channels 0,1,2,3 --failed 0:bpfo ;;
	1) run 1 "$CACHE/ims_1st_test_3200hz.npz" --channels 0,2,4,6 --failed 2:bpfi,3:bsf ;;
	all)
		run 2 "$CACHE/ims_2nd_test_3200hz.npz" --channels 0,1,2,3 --failed 0:bpfo
		run 1 "$CACHE/ims_1st_test_3200hz.npz" --channels 0,2,4,6 --failed 2:bpfi,3:bsf
		;;
	*) echo "pakai: bash scripts/evaluate.sh [1|2|all]" && exit 1 ;;
esac
