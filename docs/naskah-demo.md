# Naskah video demo SIAGA (4–5 menit)

Satu kalimat yang harus tertinggal di kepala penonton: **dari getaran sampai permintaan
pembelian, tanpa tangan manusia, di ERP yang sungguhan.**

## Persiapan sebelum merekam

```bash
bash scripts/reset_demo.sh           # semua ke titik awal
REPLAY_SPEED=0 docker compose --profile replay run --rm edge   # riwayat 7 hari sudah di Timescale
```

Tunggu satu siklus AI (30 s). Pastikan: 4 profil *Dipantau*, 4 work order otomatis
*Terbuka*, 1 Material Request *Pending*, notifikasi Telegram sudah masuk. Buka tab
browser berikut lebih dulu, urut:

1. `localhost:8080/app/siaga` — workspace
2. Asset → Pompa Dewatering Unit 01, gulir ke *Tren Kondisi*
3. SIAGA Work Order → WO otomatis untuk Unit 01
4. Material Request → draft Pending
5. Laporan Lead Time Deteksi
6. HP dengan Telegram terbuka, atau tangkapan layarnya

Jangan merekam proses replay; itu 16 menit membosankan. Rekam *keadaan setelahnya* dan
ceritakan apa yang terjadi.

## Naskah

**0:00 — Masalah (30 detik).** Layar: workspace SIAGA.
> Di tambang, alat yang berhenti tak terencana lebih mahal dari apa pun di akuntansi.
> Maintenance jalan dari kalender, data sensor berhenti di dashboard, dan dari "ada yang
> aneh" sampai "part dipesan" diisi WhatsApp dan spreadsheet. SIAGA menyambung sensor
> sampai permintaan pembelian, di dalam ERPNext.

**0:30 — Datanya (30 detik).** Layar: form Unit 01, grafik ciri ternormalisasi.
> Ini data getaran sungguhan: dataset run-to-failure NASA, empat bearing di satu poros,
> direkam sampai bearing 1 rusak. Edge tidak mengirim gelombang mentah — 25 ciri hasil
> FFT tiap cuplikan, dengan laju cuplik yang dipilih dari batas ESP32 supaya nanti
> hardware tinggal menggantikan proses ini. Lima hari datar, lalu ini.
> *(tunjuk lonjakan di ujung kanan)*

**1:00 — Skor (45 detik).** Gulir ke grafik skor kesehatan.
> Tiap unit punya modelnya sendiri, dilatih dari tiga hari pertama saat sehat. Skor 85
> selama lima hari, mulai turun 36 jam sebelum akhir, menembus ambang 40 tiga kali
> berturut-turut 25 jam sebelum rig berhenti. Garis putus-putus ini ambang pemicu dan
> ambang pulih — histeresis, supaya skor yang bergetar di sekitar ambang tidak membanjiri
> planner. Dan pill merah ini: alarm, dengan work order yang diterbitkannya.

**1:45 — Work order (60 detik).** Klik pill → form WO otomatis.
> Ini yang diterbitkan sistem. Bukan hanya "ada anomali": *ciri mana* yang menyimpang,
> berapa kali baseline, dan gejala apa yang ditebak. *(tunjuk tabel rincian pemicu)*
> Jujur: tebakannya "kenaikan getaran lebar", bukan "outer race" — pada 3,2 kHz
> lokalisasi memang lemah, dan sistem tidak berpura-pura. Yang penting: komponen dugaan
> dan part-nya sudah terisi dari konfigurasi kelas alat, dan bearing di gudang sudah
> **dikunci** untuk pekerjaan ini. *(menu Lihat → Reservasi Part)*

**2:45 — Pembelian (30 detik).** Menu Lihat → Material Request.
> Stok tersedia jatuh dari dua ke satu, di bawah titik pesan ulang. Draft permintaan
> pembelian terbit dalam siklus yang sama. Empat unit kena alarm, tapi hanya *satu*
> draft — sistem tidak membuat empat permintaan untuk part yang sama. Ini satu-satunya
> tempat manusia harus mengklik: procurement menyetujui.

**3:15 — Telegram (20 detik).** Tangkapan layar HP.
> Planner tidak perlu membuka ERP untuk tahu. Alarm, draft pembelian, dan ringkasan pagi
> masuk ke Telegram dengan tautan ke dokumennya. Dan mekanik tidak perlu membuka ERP untuk
> bekerja: tombol *Mulai kerja* dan *Selesai* di pesan alarm, tiga pertanyaan, work order
> tertutup dengan catatan kerusakan — sebagai user ERPNext yang tertaut ke chat itu.

**3:35 — Menutup lingkaran (40 detik).** WO yang sudah Selesai → laporan Lead Time.
> Saat mekanik menutup work order, ia mencatat apa yang sebenarnya rusak. Itu jadi
> label. Laporan ini dihitung sistem dari catatannya sendiri: 25,5 jam lead time,
> tebakan gejala "Umum". Angka yang bisa salah, dan sistem yang tahu kalau salah —
> itu yang tidak dimiliki forecast berdasarkan rata-rata.

**4:15 — Penutup (30 detik).** Kembali ke workspace, atau terminal `docker compose ps`.
> Semuanya ERPNext v15 dengan satu custom app, TimescaleDB, Mosquitto, dan tiga service
> Python. `docker compose up` di mesin bersih, dua menit sampai data demo siap. Kode,
> keputusan arsitektur, dan hal-hal yang tidak berhasil ada di README.
> Berikutnya: ESP32 di pompa sungguhan, lewat kontrak antarmuka yang sudah dikunci.

## Yang jangan dilakukan

- Jangan bilang "AI memprediksi bearing mana yang rusak". Bilang "sistem menandai poros
  ini 1,5 hari lebih awal, dan skor Unit 01 jatuh paling cepat".
- Jangan sebut "prediksi sisa umur". Sebut "proyeksi tren ke ambang".
- Jangan lewatkan bagian jujur. Penilai teknis mempercayai orang yang tahu batas alatnya.
