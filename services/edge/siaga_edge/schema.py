"""Definisi vektor ciri yang dikirim edge ke gateway.

Ini adalah kontrak antarmuka ke hardware: virtual edge hari ini dan firmware
ESP32 di v1.5 harus menghasilkan nama dan urutan ciri yang persis sama. Setiap
perubahan di sini menaikkan SCHEMA_VERSION, dan gateway menolak versi yang
tidak dikenalnya.
"""

SCHEMA_VERSION = 1

# Ciri domain waktu, dihitung atas seluruh blok 10 detik.
TIME_FEATURES = (
    "vib_rms",
    "vib_peak",
    "vib_p2p",
    "vib_crest",
    "vib_kurtosis",
    "vib_skewness",
)

# Amplitudo pada kelipatan putaran poros. Naiknya 1x menandakan unbalance,
# 2x menandakan misalignment, 3x ke atas menandakan kelonggaran dudukan.
ORDER_FEATURES = (
    "ord_1x",
    "ord_2x",
    "ord_3x",
)

# Energi pada frekuensi cacat bearing, dihitung dari geometri di Asset Class.
BEARING_FEATURES = (
    "bpfo_energy",
    "bpfi_energy",
    "bsf_energy",
    "ftf_energy",
)

# Delapan pita selebar 200 Hz menutup 0 sampai 1600 Hz, yaitu batas Nyquist
# pada laju cuplik 3.2 kHz.
BAND_EDGES_HZ = (0, 200, 400, 600, 800, 1000, 1200, 1400, 1600)
BAND_FEATURES = tuple(
    "band_%d_%d" % (BAND_EDGES_HZ[i], BAND_EDGES_HZ[i + 1])
    for i in range(len(BAND_EDGES_HZ) - 1)
)

SPECTRAL_SHAPE_FEATURES = (
    "spec_centroid",
    "hf_ratio",
)

# Kanal skalar, tidak lewat FFT.
SCALAR_FEATURES = (
    "current_rms",
    "temperature_c",
)

FEATURE_NAMES = (
    TIME_FEATURES
    + ORDER_FEATURES
    + BEARING_FEATURES
    + BAND_FEATURES
    + SPECTRAL_SHAPE_FEATURES
    + SCALAR_FEATURES
)

FEATURE_COUNT = len(FEATURE_NAMES)
