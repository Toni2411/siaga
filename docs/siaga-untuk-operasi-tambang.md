# SIAGA dilihat dari sisi operasi tambang

*Satu halaman untuk pembaca yang mengurus alat, bukan yang menulis kode: apa
yang dikerjakan sistem ini, KPI mana yang disentuhnya, dan apa yang belum.*

## Masalah yang dikejar

Pada armada alat, biaya terbesar bukan harga spare part, melainkan **jam yang
hilang saat alat berhenti tak terencana**. Tiga jeda yang membuatnya mahal:

1. **Jeda deteksi.** Kerusakan bearing berkembang berhari-hari sebelum alat
   berhenti, tapi baru diketahui saat sudah bunyi atau panas.
2. **Jeda dokumen.** Temuan ada di kepala mekanik atau di dashboard vendor
   sensor; work order ada di ERP; permintaan pembelian dibuat orang lain
   beberapa hari kemudian setelah rapat.
3. **Jeda part.** Bearing dipesan setelah alat berhenti, padahal lead time
   pengadaannya bisa berminggu-minggu.

Maintenance berbasis kalender tidak menutup satu pun dari ketiganya. Ia
mengganti komponen yang masih sehat, dan tetap kecolongan komponen yang rusak
lebih cepat dari jadwalnya.

## Apa yang dikerjakan sistem

Tujuh langkah, dari getaran sampai tanda tangan procurement, di dalam satu ERP:

| # | Langkah | Hasilnya |
| --- | --- | --- |
| 1 | Sensor di alat mengirim 25 ciri getaran tiap cuplikan | Riwayat kondisi per unit |
| 2 | Tiap unit dinilai terhadap kondisi sehatnya sendiri | Skor kesehatan 0–100 |
| 3 | Skor jatuh dan bertahan di bawah ambang | Work order terbit otomatis |
| 4 | Work order membawa komponen dan part dugaan | Mekanik tidak mulai dari nol |
| 5 | Part dikunci untuk pekerjaan itu | Tidak dipakai work order lain |
| 6 | Stok tersedia jatuh di bawah titik pesan | Draft permintaan pembelian terbit |
| 7 | Planner dan procurement menyetujui | Satu-satunya langkah manual |

Dan satu langkah yang berjalan **sebelum** alarm: begitu tren skor sebuah unit
mantap menuju ambang, kebutuhan part-nya dihitung dan permintaan pembelian
terbit lebih awal, dengan alasan tertulis di dokumennya.

Mekanik menutup work order dari HP lewat Telegram, dan mencatat **apa yang
sebenarnya rusak**. Catatan itu yang membuat sistem bisa dinilai.

## KPI yang disentuh

| KPI | Bagaimana sistem menyentuhnya |
| --- | --- |
| **PA** (Physical Availability) | Kerusakan yang ditangani sebelum berhenti mendadak memindahkan downtime dari *unplanned* ke *planned*, dan durasinya lebih pendek karena part sudah ada |
| **UA** (Use of Availability) | Tidak langsung; sistem tidak mengatur pola operasi |
| **MTTR** | Turun karena work order sudah membawa dugaan komponen dan part-nya sudah dikunci di gudang — bukan mulai dari mencari penyebab |
| **MTBF** | Naik bila penggantian dilakukan tepat waktu, bukan setelah kerusakan merambat ke komponen lain |
| **Inventory** | Part dipesan karena *unit tertentu* akan membutuhkannya, bukan karena rata-rata pemakaian bulan lalu |

Laporan **Ketersediaan Alat** menghitung PA, UA, MA, MTBF, dan MTTR per unit.
Yang membedakannya dari lembar shift: **jam operasi diambil dari status alat
yang dikirim sensor**, bukan dari catatan tangan. Angka availability yang
dihitung dari kondisi alat sendiri lebih sulit diperdebatkan antara kontraktor
dan owner.

Laporan **Lead Time Deteksi** menutup lingkaran penilaian: untuk tiap kerusakan
yang dicatat mekanik, berapa jam sebelumnya sistem sudah menandainya, dan
apakah tebakan gejalanya benar. Sistem yang mengukur kesalahannya sendiri.

## Angka dari pengujian

Diuji pada dataset *run-to-failure* bearing milik NASA — bukan data tambang,
dan itu disebut terang-terangan. Empat bearing pada satu poros, direkam sampai
rusak.

| Rig | Kejadian | Peringatan sebelum berhenti |
| --- | --- | --- |
| Set 2, 7 hari | Kerusakan outer race | **25,5 jam** |
| Set 1, 35 hari | Kerusakan inner race | **80,5 jam** |
| Set 1 | Kerusakan elemen gelinding | **128 jam** |
| Set 1 | Unit sehat, 35 hari, 9 kali restart | Tidak pernah memicu alarm palsu |

Draft permintaan pembelian terbit **44 jam sebelum rig berhenti**, 19 jam
sebelum alarm, saat skor masih 70.

## Yang belum, dan tidak dijanjikan

- **Datanya bukan dari tambang.** Dataset publik dari rig uji laboratorium.
  Pompa dewatering di demo adalah empat kanal dataset itu.
- **Sensornya belum ada.** Pengambilan ciri dijalankan dari rekaman; laju
  cuplik 3,2 kHz sengaja dipilih dari batas ESP32 supaya firmware nanti tinggal
  menggantikan bagian itu tanpa mengubah apa pun di hilir.
- **Lokalisasi cacat lemah** pada laju cuplik itu. Sistem menyebut "kenaikan
  getaran lebar", bukan "cacat outer race", kalau memang tidak yakin.
- **Proyeksi hari ke ambang adalah ekstrapolasi tren**, bukan prediksi sisa
  umur. Ia terlalu optimis pada degradasi yang mempercepat, dan dipakai sebagai
  tanda kebutuhan, bukan sebagai tanggal.
- **Durasi perbaikan di data demo adalah ilustrasi.** Dataset merekam rig yang
  berjalan sampai gagal; tidak ada peristiwa perbaikan di dalamnya.
- **Satu kelas alat.** Pompa bermotor listrik. Alat berat bergerak menuntut
  pemodelan beban yang berbeda.

## Kalau dipasang di armada sungguhan

Empat hal yang harus ada lebih dulu, berurutan:

1. **Data kondisi yang bisa dibaca sistem.** Banyak alat sudah punya pemantauan
   dari pabrikan; pertanyaan pertama bukan "sensor apa", melainkan "data yang
   sudah ada bisa keluar lewat apa".
2. **Master data yang rapi di ERP.** Unit, komponen, part kandidat per gejala,
   titik pesan ulang per gudang. Tanpa ini, otomasi hanya memindahkan kekacauan.
3. **Baseline sehat per unit.** Beberapa hari data saat alat normal, dan aturan
   yang tahu bahwa baseline tidak berlaku lagi setelah shutdown panjang atau
   penggantian komponen.
4. **Kesepakatan siapa yang menyetujui apa.** Sistem menerbitkan draft; manusia
   tetap yang menandatangani. Itu keputusan desain, bukan keterbatasan.
