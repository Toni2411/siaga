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

Minggu 1 dari 8 selesai.

| Bagian | Status |
| --- | --- |
| Stack Docker: ERPNext v15, TimescaleDB, Mosquitto | Jalan, semua layanan terverifikasi |
| Custom app `siaga` | Terpasang di site, DocType menyusul minggu 2 |
| Virtual edge, DSP dan ekstraksi ciri | Selesai, 22 tes lolos |
| Replay service | Belum |
| AI service | Belum |

## Menjalankan tes

Satu satunya bagian yang bisa dicoba sekarang, dan tidak butuh Docker.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install numpy pytest   # Linux/macOS: .venv/bin/python
cd services/edge
../../.venv/Scripts/python.exe -m pytest -q
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

App `siaga` dibangun ke dalam image supaya worker dan scheduler juga
memuatnya, lalu foldernya di-bind-mount sehingga perubahan kode Python
langsung terbaca. Kalau `hooks.py` atau DocType berubah, jalankan
`docker compose restart backend queue-short queue-long scheduler`.

## Susunan repo

```
apps/siaga/          custom app Frappe, berjalan di dalam ERPNext
services/edge/       virtual edge: DSP dan ekstraksi ciri dari gelombang mentah
services/replay/     pemutar dataset run to failure jadi aliran waktu nyata
services/ai/         deteksi anomali, skor kesehatan, pemicu work order
docker/              konfigurasi Mosquitto dan skema TimescaleDB
scripts/             utilitas pemasangan
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

Contoh perilakunya, cacat outer race yang disuntikkan bertahap:

| ciri | sehat | awal | berkembang |
| --- | --- | --- | --- |
| `bpfo_energy` | 0.033 | 0.316 | 0.945 |
| `bpfi_energy` | 0.030 | 0.030 | 0.030 |
| `ord_1x` | 0.465 | 0.465 | 0.465 |

Energi BPFO naik 29 kali sementara BPFI dan amplitudo 1x poros tidak bergerak.
Inilah yang membuat sistem bisa menyebut komponen mana yang rusak, bukan
sekadar melaporkan ada anomali.
