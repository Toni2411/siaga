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

Minggu 3 dari 8 selesai.

| Bagian | Status |
| --- | --- |
| Stack Docker: ERPNext v15, TimescaleDB, Mosquitto | Jalan, semua layanan terverifikasi |
| Custom app `siaga` | 6 DocType, field tambahan di Asset, workspace, seed demo |
| Virtual edge: replay dataset IMS, DSP, ekstraksi ciri, MQTT | Jalan di Docker, 46 tes |
| Gateway: MQTT ke TimescaleDB | Jalan di Docker, ~400 pesan/detik |
| Grafik tren di ERPNext | Minggu 4 |
| AI service | Minggu 5 |

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
`scripts/reset_timeseries.sh`.

App `siaga` dibangun ke dalam image supaya worker dan scheduler juga
memuatnya, lalu foldernya di-bind-mount sehingga perubahan kode Python
langsung terbaca. Kalau `hooks.py` atau DocType berubah, jalankan
`docker compose restart backend queue-short queue-long scheduler`.

## Susunan repo

```
apps/siaga/          custom app Frappe, berjalan di dalam ERPNext
services/edge/       virtual edge: replay dataset, DSP, ekstraksi ciri, penerbit MQTT
services/gateway/    pelanggan MQTT yang menulis ke TimescaleDB
services/ai/         deteksi anomali, skor kesehatan, pemicu work order (minggu 5)
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
