app_name = "siaga"
app_title = "SIAGA"
app_publisher = "SIAGA"
app_description = "Maintenance berbasis kondisi dan otomasi procurement untuk alat tambang"
app_email = "semscapstone24@gmail.com"
app_license = "mit"

# DocType yang dimiliki app ini didaftarkan otomatis lewat modules.txt.
# Yang menyusul di minggu 2: Asset Class, Asset Component, Asset Monitoring
# Profile, Health Score, SIAGA Work Order, Part Reservation, Failure Log.

# Field tambahan pada DocType bawaan ERPNext. Ditambahkan lewat fixtures
# supaya ikut terpasang di site mana pun tanpa diklik manual.
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "SIAGA"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "SIAGA"]]},
]

# JS tambahan untuk DocType bawaan: grafik tren kondisi di form Asset.
doctype_js = {"Asset": "public/js/asset.js"}

# Skor kesehatan yang baru masuk dievaluasi terhadap aturan pemicu; kalau
# lolos, work order otomatis terbit dalam transaksi yang sama.
doc_events = {
    "Health Score": {"after_insert": "siaga.automation.on_health_score"},
}

scheduler_events = {
    # Ringkasan pagi ke Telegram: unit dalam alarm, work order terbuka,
    # draft pembelian menunggu. Diam kalau Telegram tidak dikonfigurasi.
    "daily": ["siaga.telegram.daily_summary"],
}
