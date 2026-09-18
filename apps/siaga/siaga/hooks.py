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

# Diisi di minggu 6, saat webhook penutupan work order mulai mengalir balik ke
# AI service sebagai label pelatihan.
doc_events = {}

# Diisi di minggu 5, untuk penyegaran titik pesan ulang dari hasil forecast.
scheduler_events = {}
