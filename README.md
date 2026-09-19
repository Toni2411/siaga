# SIAGA

Maintenance berbasis kondisi dan otomasi procurement untuk alat tambang,
dibangun sebagai custom app di atas ERPNext.

Sistem membaca getaran dan arus alat, mendeteksi degradasi komponen,
menerbitkan work order, mengunci spare part, dan menyiapkan draft permintaan
pembelian. Manusia hanya masuk di titik approval. Rancangan lengkapnya ada di
[PRD](PRD%20SIAGA%20—%20ERP%20Maintenance%20&%20Asset%20Management%20Tambang.md).

V1 dibangun tanpa perangkat keras. Sumber getarannya adalah dataset run to
failure publik yang diputar ulang sebagai aliran waktu nyata. ESP32 masuk di
v1.5 lewat antarmuka yang sama persis.

## Status

Minggu 7 dari 8 selesai. Rantai tujuh langkah jalan penuh, dan lingkarannya tertutup lewat catatan kerusakan.

| Bagian | Status |
| --- | --- |
| Stack Docker: ERPNext v15, TimescaleDB, Mosquitto | Jalan, semua layanan terverifikasi |
| Custom app `siaga` | 9 DocType, work order otomatis dari skor kesehatan, reservasi part, Material Request otomatis, grafik skor dan tren di form Asset |
| Virtual edge: replay dataset IMS, DSP, ekstraksi ciri, MQTT | Jalan di Docker, 46 tes |
| Gateway: MQTT ke TimescaleDB | Jalan di Docker, ~400 pesan/detik |
| AI service: model per unit, skor kesehatan, proyeksi, penjelasan pemicu | Jalan di Docker, 15 tes |

## Menjalankan tes

Tidak butuh Docker.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e services/edge -e services/gateway pytest   # Linux/macOS: .venv/bin/python
cd services/edge   && ../../.venv/Scripts/python.exe -m pytest -q
cd ../gateway      && ../../.venv/Scripts/python.exe -m pytest -q
```

## Menjalankan stack

Butuh Docker Desktop dengan backend WSL2, dan sekitar 6 GB RAM bebas.

```bash
cp .env.example .env            # ubah password di dalamnya
docker compose up -d --build    # unduhan pertama kali sekitar 7 GB
./scripts/install-siaga.sh
```

Pemasangan ERPNext ke database baru memakan beberapa menit. Setelah itu buka
`http://localhost:8080`, login sebagai `Administrator` dengan password dari
`.env`, dan selesaikan setup wizard.

Lalu isi data demo, yang membuat kelas alat pertama beserta aset contohnya:

```bash
python scripts/seed_demo.py
```

## Mengalirkan data

Sumber getaran v1 adalah dataset bearing IMS dari NASA Prognostics Center of
Excellence: empat bearing pada satu poros 2000 RPM, direkam tiap sepuluh
menit sampai bearing 1 rusak di outer race setelah tujuh hari. Skrip berikut
mengunduh (1 GB), membongkar tiga lapis arsip, menurunkan laju cuplik ke
3.2 kHz, dan menyimpan cache 45 MB. Butuh scipy, pandas, py7zr, dan alat
pembuka rar (tar bawaan Windows 11 cukup).

```bash
.venv/Scripts/python.exe -m pip install scipy pandas py7zr
.venv/Scripts/python.exe scripts/prepare_dataset.py
```

Gateway sudah hidup bersama stack. Untuk memutar dataset lewat MQTT:

```bash
docker compose --profile replay up edge          # 7 hari data dalam 16 menit
REPLAY_SPEED=0 docker compose --profile replay run --rm edge   # tanpa jeda, sekitar 10 detik
```

Tiap putaran memasang cap waktu virtual yang berakhir sekarang, jadi replay
ulang menghasilkan riwayat kedua yang bergeser. Kosongkan dulu dengan
`scripts/reset_timeseries.sh`, dan `scripts/reset_monitoring.sh` untuk
mengosongkan skor dan model supaya semuanya dinilai ulang.

## AI service

Berjalan terus di container `ai` dan memanggil ERPNext sebagai user
`siaga-bot` dengan API key (dibuat lewat menu User, lalu isi
`ERPNEXT_API_KEY` dan `ERPNEXT_API_SECRET` di `.env`). Tiap siklus, untuk
tiap Asset Monitoring Profile:

1. `Belum terdaftar` → begitu ada data, mulai mengumpulkan baseline.
2. `Mengumpulkan baseline` → setelah `baseline_days` data sehat, latih model
   per unit dan simpan di volume `models`.
3. `Dipantau` → nilai tiap cuplikan baru yang kondisinya stabil, tulis
   Health Score: skor 0–100, ciri yang paling menyimpang, gejala, dan
   proyeksi hari ke ambang bila trennya turun.

Skor yang masuk dievaluasi hook `after_insert` di ERPNext
(`siaga/automation.py`): kalau skor di bawah ambang pemicu kelas selama
`consecutive_cycles` berturut turut dan profil belum dalam status Alarm,
work order otomatis terbit dan langsung submit, dengan komponen dan part
dugaan dari tabel part kandidat kelas menurut gejala. Reservasi part dan
draft Material Request menyusul dari controller work order. Profil masuk
status Alarm sampai skor naik melewati ambang pulih (histeresis), dan
planner menerima notifikasi lonceng. `scripts/reset_demo.sh` mengembalikan
semuanya ke titik awal supaya rantai bisa diputar ulang.

Saat mekanik menyelesaikan work order, ia mencatat apa yang sebenarnya
rusak; itu jadi Failure Log dengan label pelatihan, dan komponen ditandai
diganti. Laporan **Lead Time Deteksi** membandingkan waktu pemicu sistem
dengan waktu kerusakan yang dicatat, dan gejala tebakan dengan label
sebenarnya. Pada dataset IMS: pemicu 24,7 jam sebelum rig berhenti, gejala
tebakan "kenaikan getaran lebar" untuk kerusakan outer race, dinilai "Umum"
karena tidak salah tapi tidak menunjuk. Setelah komponen diganti, tombol
*Kumpulkan Baseline Ulang* di profil membuat model unit itu dilatih ulang.

Modelnya Isolation Forest digabung jarak z robust per ciri, keduanya
dikalibrasi ke tepi baseline unit itu sendiri. Pada dataset IMS, skor
bearing 1 bertahan di atas 80 selama lima hari, turun ke 50 sekitar 36 jam
sebelum akhir, dan memicu ambang 40 tiga siklus berturut turut sekitar 24
jam sebelum rig dimatikan. Tiga bearing lain di poros yang sama ikut turun
belakangan karena getaran merambat; di tambang sungguhan empat pompa tidak
berbagi poros. Gejala spesifik bearing hanya disebut kalau ciri bearingnya
jelas melampaui tepi baseline; selebihnya ditulis apa adanya sebagai
kenaikan getaran lebar, karena pada 3.2 kHz lokalisasi cacat memang lemah.

App `siaga` dibangun ke dalam image supaya worker dan scheduler juga
memuatnya, lalu foldernya di-bind-mount sehingga perubahan kode Python
langsung terbaca. Kalau `hooks.py` atau DocType berubah, jalankan
`docker compose restart backend queue-short queue-long scheduler`.

## Susunan repo

```
apps/siaga/          custom app Frappe, berjalan di dalam ERPNext
services/edge/       virtual edge: replay dataset, DSP, ekstraksi ciri, penerbit MQTT
services/gateway/    pelanggan MQTT yang menulis ke TimescaleDB
services/ai/         model per unit, skor kesehatan, proyeksi tren, penjelasan pemicu
docker/              konfigurasi Mosquitto dan skema TimescaleDB
scripts/             penyiapan dataset, seed demo, utilitas
data/                dataset dan cache, tidak masuk git
```

## Virtual edge

Bagian ini yang paling layak dibaca lebih dulu, karena memuat keputusan teknis
yang mengikat sisa sistem.

Getaran tidak pernah dikirim mentah. Edge mencuplik pada 3.2 kHz, menghitung
FFT 1024 titik, lalu menerbitkan 25 ciri tiap 10 detik. Bandwidth turun ribuan
kali lipat, dan model bekerja di atas fitur yang punya arti fisik sehingga
work order bisa menjelaskan alasan pemicunya.

Laju 3.2 kHz diambil dari batas ESP32 dan ADXL345, bukan dari kenyamanan
simulasi. Nyquist 1.6 kHz masih jauh di atas frekuensi cacat bearing pada
kelas alat pertama, yaitu 236 Hz untuk outer race dan 297 Hz untuk inner race,
jadi model yang dilatih sekarang tetap sahih saat sumbernya diganti perangkat
fisik.

Seluruh modul hanya bergantung pada numpy, dan tiap operasinya punya padanan
langsung di ESP-DSP. Versi Python ini jadi rujukan kebenaran saat porting ke
C++: firmware dianggap lulus kalau menghasilkan angka yang sama untuk gelombang
uji yang sama.

Pesan MQTT-nya adalah kontrak: `siaga_edge/message.py` mendefinisikan dan
memvalidasinya, gateway menolak apa pun yang tidak lolos, dan firmware v1.5
harus menghasilkan pesan yang sama. Dua kanal skalar, arus dan suhu, tidak
ada di dataset dan diisi nilai nominal berderau; pesan menandainya
`synthetic` supaya tidak ada yang mengira itu pengukuran.

Pada data IMS sungguhan, energi BPFO bearing 1 stabil selama lima hari lalu
naik tiga kali lipat dalam dua jam terakhir sebelum rig dimatikan, sementara
bearing 2 di poros yang sama ikut naik belakangan dan lebih lemah. Dua
cuplikan terakhir terbaca `mati` karena RMS-nya nol, yang menjadi alasan
gating kondisi operasi.

Contoh perilakunya pada sinyal sintetis, cacat outer race yang disuntikkan bertahap:

| ciri | sehat | awal | berkembang |
| --- | --- | --- | --- |
| `bpfo_energy` | 0.033 | 0.316 | 0.945 |
| `bpfi_energy` | 0.030 | 0.030 | 0.030 |
| `ord_1x` | 0.465 | 0.465 | 0.465 |

Energi BPFO naik 29 kali sementara BPFI dan amplitudo 1x poros tidak bergerak.
Inilah yang membuat sistem bisa menyebut komponen mana yang rusak, bukan
sekadar melaporkan ada anomali.
