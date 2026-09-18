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
- `SIAGA Work Order` — work order maintenance, submittable. Saat submit: mereservasi part, lalu menerbitkan draft Material Request kalau stok setelah reservasi jatuh di bawah titik pesan ulang. Saat selesai: mengeluarkan part lewat Stock Entry Material Issue
- `SIAGA Work Order Part` — child table: part yang dibutuhkan, dengan stok tersedia setelah reservasi
- `Part Reservation` — janji stok untuk satu work order: Aktif, Dilepas, atau Dipakai

Field tambahan lewat fixtures: di `Asset` ada `asset_class`, `operating_hours`
(keduanya boleh diubah setelah submit) dan `siaga_trend` (grafik tren kondisi,
dirender `public/js/asset.js` dari data TimescaleDB lewat `api/timeseries.py`);
di `Material Request` ada `siaga_auto` dan `siaga_work_order`.

Aturan yang dijaga controller work order: satu work order terbuka per
pasangan aset dan komponen (keras untuk pemicu Otomatis, peringatan untuk
Manual), dan satu draft Material Request per item per gudang.

## Cara mengubah DocType

Site pengembangan berjalan dalam developer mode, jadi ubah DocType lewat UI
Frappe (menu Customize atau DocType langsung) dan Frappe menulis JSON-nya ke
folder ini. Jangan edit JSON dengan tangan. Controller Python di folder
`doctype/<nama>/<nama>.py` diedit langsung, lalu restart backend.

## Pemasangan

Lihat README di akar repo.
