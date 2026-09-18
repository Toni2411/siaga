# siaga

Custom app Frappe untuk SIAGA. Menambahkan maintenance berbasis kondisi dan
otomasi procurement di atas ERPNext, tanpa mengubah core.

App ini sengaja terpisah dari ERPNext supaya bisa dipasang ulang di site mana
pun dan dipublikasikan sebagai karya sendiri.

## Isi

DocType yang sudah ada, semuanya di modul SIAGA:

- `Asset Class` — konfigurasi per kelas alat: RPM, geometri bearing, ambang, part kandidat
- `Asset Component` — komponen di dalam satu aset beserta umur desainnya
- `Asset Monitoring Profile` — status pemantauan dan versi model per unit
- `Health Score` — skor, proyeksi hari ke ambang, pemicu, keyakinan
- `Failure Log` — apa yang sebenarnya rusak, jadi label pelatihan ulang
- `Asset Class Candidate Part` — child table: part kandidat per gejala

Field tambahan di `Asset` bawaan lewat fixtures: `asset_class` dan
`operating_hours`, keduanya boleh diubah setelah submit.

Menyusul di minggu 4: `SIAGA Work Order` dan `Part Reservation`.

## Cara mengubah DocType

Site pengembangan berjalan dalam developer mode, jadi ubah DocType lewat UI
Frappe (menu Customize atau DocType langsung) dan Frappe menulis JSON-nya ke
folder ini. Jangan edit JSON dengan tangan. Controller Python di folder
`doctype/<nama>/<nama>.py` diedit langsung, lalu restart backend.

## Pemasangan

Lihat README di akar repo.
