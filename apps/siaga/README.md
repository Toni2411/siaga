# siaga

Custom app Frappe untuk SIAGA. Menambahkan maintenance berbasis kondisi dan
otomasi procurement di atas ERPNext, tanpa mengubah core.

App ini sengaja terpisah dari ERPNext supaya bisa dipasang ulang di site mana
pun dan dipublikasikan sebagai karya sendiri.

## Isi

Struktur masih kerangka. DocType menyusul di minggu 2 sesuai roadmap di PRD:

- `Asset Class` — konfigurasi per kelas alat: RPM, geometri bearing, ambang, part kandidat
- `Asset Component` — komponen di dalam satu aset beserta umur desainnya
- `Asset Monitoring Profile` — status pemantauan dan versi model per unit
- `Health Score` — skor, proyeksi hari ke ambang, pemicu, keyakinan
- `SIAGA Work Order` — work order maintenance, dibuat sendiri karena Work Order bawaan adalah dokumen manufaktur
- `Part Reservation` — penguncian stok untuk satu work order
- `Failure Log` — apa yang sebenarnya rusak, jadi label pelatihan ulang

## Pemasangan

Lihat README di akar repo.
