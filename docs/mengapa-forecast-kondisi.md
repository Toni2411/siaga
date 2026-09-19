# Mengapa forecast spare part berbasis kondisi mengalahkan forecast historis

*Catatan teknis dari membangun SIAGA. Angka di sini datang dari laporan sistem sendiri
pada dataset run-to-failure bearing IMS, bukan dari simulasi.*

## Dua cara meramal kebutuhan bearing

**Forecast historis** melihat ke belakang: rata-rata pemakaian bearing per bulan, dikali
lead time pengadaan, ditambah safety stock. Di ERP, ini adalah titik pesan ulang yang
dihitung dari konsumsi. Cara ini bekerja kalau kegagalan datang dengan laju yang kira-kira
tetap dan tidak terlalu jarang. Pada sepuluh pompa dengan bearing berumur dua tahun,
konsumsinya nol selama berbulan-bulan, lalu tiba-tiba dua dalam seminggu. Rata-rata tidak
menceritakan kapan.

**Forecast berbasis kondisi** melihat ke alat: bearing yang mulai rusak mengubah spektrum
getarannya berhari-hari sebelum berhenti. Kalau perubahan itu terbaca dan langsung
diterjemahkan menjadi reservasi part dan permintaan pembelian, stok dipesan *karena alat
tertentu akan membutuhkannya*, bukan karena rata-rata bilang begitu.

Perbedaannya bukan pada akurasi model. Perbedaannya pada **kapan informasi tersedia**
dan **apakah informasi itu sampai ke dokumen pembelian**.

## Apa yang terjadi pada bearing 1

Dataset IMS set 2: empat bearing pada satu poros 2000 RPM, cuplikan satu detik tiap
sepuluh menit selama tujuh hari, sampai bearing 1 gagal di outer race.

Model per unit dilatih pada tiga hari pertama. Skor kesehatan bearing 1 setelah itu,
median dua jam di sekitar tiap titik:

| Jam sebelum rig berhenti | Skor |
| --- | --- |
| 120 | 87 |
| 48 | 86 |
| 36 | 55 |
| 24 | 39 |
| 12 | 3 |
| 0 | 0 |

Pemicu — tiga skor berturut-turut di bawah 40 — jatuh **25,5 jam** sebelum rig berhenti.
Di zona sehat, keempat bearing tidak pernah sekali pun menyentuh 40 selama lima hari.

Dataset kedua, yang tidak pernah dipakai untuk menyetel apa pun, memberi angka yang lebih
besar untuk mode kegagalan yang berkembang lebih lambat: bearing dengan cacat inner race
memicu 80 jam sebelum akhir, bearing dengan cacat elemen gelinding 128 jam. Unit sehat di
rig itu bertahan di skor 90 selama sebulan dan sembilan restart tanpa satu pun pemicu.

Pada saat pemicu, reservasi bearing di gudang membuat stok tersedia jatuh dari 2 ke 1,
di bawah titik pesan ulang, dan draft Material Request terbit dalam siklus yang sama.
Procurement melihat permintaan itu sehari sebelum kegagalan — bukan sehari sesudahnya.

Dan sebenarnya lebih awal dari itu. Proyeksi tren bearing 1 menjadi *mantap* — tiga
siklus berturut-turut, seluruh interval di dalam horizon 14 hari — sekitar 44
jam sebelum rig berhenti, 19 jam sebelum alarm. Pada titik itu skor
masih 70, belum ada work order, tapi kebutuhan satu bearing sudah dihitung:
stok tersedia 2 dikurangi kebutuhan terproyeksi 1 jatuh di bawah titik pesan ulang, dan
draft Material Request terbit dengan alasan tertulis: "proyeksi ke ambang ~5
hari". Ketika alarm datang, reservasinya menemukan draft yang sudah ada.

Angka "5 hari"-nya sendiri meleset: rig berhenti 1,8 hari kemudian, karena degradasi
bearing mempercepat dan ekstrapolasi linear selalu terlambat mengejarnya. Itu bukan alasan
menunggu proyeksi yang lebih akurat. Yang dibutuhkan procurement bukan tanggal yang tepat,
melainkan kepastian bahwa unit ini akan membutuhkan bearing dalam waktu dekat — dan itu
sudah cukup pasti dua hari sebelumnya.

Forecast yang ini tidak pernah bisa dibuat dari konsumsi historis: rata-rata pemakaian
bearing di gudang itu, dihitung sistem dari Material Issue 90 hari terakhir, sekitar satu
per bulan. Laporan *Forecast Part* menaruh kedua angka berdampingan.

## Yang tidak dijanjikan

Sehari terdengar sedikit dibanding lead time pengadaan bearing yang bisa berminggu-minggu.
Tiga hal perlu diluruskan.

Pertama, sehari sampai lima hari adalah angka pada dataset ini, dengan laju cuplik 3,2 kHz yang dipilih
karena itu batas ESP32 dan akselerometer murah. Degradasi bearing 1 sudah terlihat pada
pita 600–1200 Hz sekitar 36 jam sebelum akhir; ambang dan aturan tiga siklus sengaja
konservatif supaya tidak ada alarm palsu. Sistem bisa disetel lebih agresif dengan harga
alarm palsu yang lebih sering, dan harga itu ditanggung planner, bukan model.

Kedua, nilai forecast berbasis kondisi tidak hanya pada part yang *belum ada*. Pada part
yang *ada*, ia mengubah pemakaian dari "ganti karena jadwal" menjadi "ganti karena perlu".
Bearing yang sehat tidak diganti pada jam ke-250 hanya karena kalender bilang begitu.
Penghematannya ada di part yang tidak jadi dibeli.

Ketiga, tebakan gejala sistem pada saat pemicu adalah "kenaikan getaran lebar", bukan
"cacat outer race". Pada 3,2 kHz tanpa envelope analysis, lokalisasi memang lemah.
Laporan sistem menilai tebakan itu "Umum" — tidak salah, tidak menunjuk. Kalau part
kandidat untuk gejala umum dikonfigurasi dengan benar (bearing sisi kopling untuk pompa),
work order tetap membawa part yang tepat; kalau tidak, mekanik yang memastikan saat
inspeksi. Sistem tidak berpura-pura tahu lebih dari yang dilihatnya.

## Apa yang sebenarnya diselesaikan

Yang mahal di operasi tambang bukan algoritma deteksi. Yang mahal adalah jeda: deteksi
ada di dashboard vendor sensor, work order ada di ERP, permintaan pembelian dibuat orang
lain seminggu kemudian setelah rapat. Setiap sambungan diisi manusia yang sibuk.

SIAGA menghapus sambungan itu. Skor masuk, work order terbit, part dikunci, permintaan
pembelian menunggu tanda tangan — di bawah satu menit, di sistem yang sama tempat
procurement bekerja. Sehari lebih awal dengan dokumen yang sudah siap mengalahkan tiga
hari lebih awal di dashboard yang tidak dibuka siapa pun.

Dan karena mekanik mencatat apa yang sebenarnya rusak saat menutup work order, sistem
mengukur dirinya sendiri: lead time nyata, tebakan yang benar dan yang salah. Forecast
historis tidak pernah tahu seberapa salah dirinya. Forecast berbasis kondisi tahu, per
kejadian.
