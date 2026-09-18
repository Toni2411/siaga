"""Ekstraksi vektor ciri dari gelombang getaran mentah.

Semua operasi di sini sengaja dibatasi pada aritmetika dasar dan satu FFT real,
supaya punya padanan langsung di ESP-DSP saat firmware ditulis di v1.5. Modul
ini hanya bergantung pada numpy, dan versi Python-nya jadi rujukan kebenaran
saat porting ke C++.
"""

from __future__ import annotations

import numpy as np

from .config import AssetClassConfig
from .schema import BAND_EDGES_HZ, FEATURE_NAMES


def _hann(n: int) -> np.ndarray:
    # Ditulis eksplisit, bukan np.hanning, supaya definisinya sama persis
    # dengan yang nanti ditanam di perangkat.
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)


def _energy_correction(n: int) -> float:
    """Koreksi energi jendela Hann.

    Spektrum di bawah dikoreksi dengan coherent gain supaya amplitudo tone
    terbaca benar. Untuk hitungan daya per pita koreksi itu berlebih 1.5 kali,
    karena jendela menyebarkan energi tone ke bin tetangga. Faktor ini
    mengembalikannya, sehingga RMS pita cocok dengan RMS domain waktu.
    """
    w = _hann(n)
    return float(w.mean() ** 2 / (w * w).mean())


def averaged_amplitude_spectrum(
    signal: np.ndarray, cfg: AssetClassConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Spektrum amplitudo rata rata ala Welch, jendela Hann, tumpang tindih 50%.

    Merata ratakan beberapa jendela menekan derau tanpa mengubah amplitudo
    komponen tonal, yang penting karena ciri cacat bearing berupa puncak sempit
    di tengah derau lebar.
    """
    n = cfg.window_size
    if signal.size < n:
        raise ValueError(
            "blok terlalu pendek: %d cuplikan, minimal %d" % (signal.size, n)
        )

    window = _hann(n)
    # Faktor koreksi amplitudo jendela. Tanpa ini amplitudo tone terbaca
    # separuh dari nilai sebenarnya.
    coherent_gain = window.mean()
    step = n // 2

    power_sum = None
    segments = 0
    for start in range(0, signal.size - n + 1, step):
        segment = signal[start : start + n]
        segment = segment - segment.mean()  # buang DC, spektrum jadi AC murni
        spectrum = np.fft.rfft(segment * window)
        amplitude = np.abs(spectrum) * (2.0 / (n * coherent_gain))
        amplitude[0] *= 0.5  # bin DC tidak punya pasangan frekuensi negatif
        if n % 2 == 0:
            amplitude[-1] *= 0.5  # begitu juga bin Nyquist
        power = amplitude * amplitude
        power_sum = power if power_sum is None else power_sum + power
        segments += 1

    power_avg = power_sum / segments
    freqs = np.fft.rfftfreq(n, d=1.0 / cfg.sample_rate_hz)
    return freqs, np.sqrt(power_avg)


def _band_rms(
    freqs: np.ndarray, amp: np.ndarray, lo: float, hi: float, corr: float
) -> float:
    """RMS dari isi spektrum dalam satu pita.

    Amplitudo puncak diubah ke RMS lewat pembagian dengan 2 pada ranah daya,
    sehingga satu tone beramplitudo A dalam pita menghasilkan A/sqrt(2).
    """
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        return 0.0
    return float(np.sqrt(np.sum(amp[mask] ** 2) * corr / 2.0))


def _peak_near(freqs: np.ndarray, amp: np.ndarray, target: float, tol: float) -> float:
    """Amplitudo puncak tertinggi di sekitar satu frekuensi sasaran."""
    if target <= 0 or target >= freqs[-1]:
        return 0.0
    mask = np.abs(freqs - target) <= tol
    if not mask.any():
        return 0.0
    return float(amp[mask].max())


def _defect_energy(
    freqs: np.ndarray,
    amp: np.ndarray,
    target: float,
    tol: float,
    harmonics: int,
    nyquist: float,
    corr: float,
) -> float:
    """RMS gabungan di sekitar frekuensi cacat dan harmonisanya.

    Harmonisa ikut dihitung karena cacat yang sudah berkembang memunculkan
    deretan puncak, bukan satu puncak tunggal.
    """
    if target <= 0:
        return 0.0
    power = 0.0
    for h in range(1, harmonics + 1):
        centre = target * h
        if centre >= nyquist:
            break
        mask = np.abs(freqs - centre) <= tol
        if mask.any():
            power += float(np.sum(amp[mask] ** 2) * corr / 2.0)
    return float(np.sqrt(power))


def _time_features(signal: np.ndarray) -> dict[str, float]:
    x = signal - signal.mean()
    rms = float(np.sqrt(np.mean(x * x)))
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    p2p = float(x.max() - x.min()) if x.size else 0.0

    if rms > 0.0:
        crest = peak / rms
        kurtosis = float(np.mean(x**4) / (rms**4))
        skewness = float(np.mean(x**3) / (rms**3))
    else:
        crest = kurtosis = skewness = 0.0

    return {
        "vib_rms": rms,
        "vib_peak": peak,
        "vib_p2p": p2p,
        "vib_crest": crest,
        "vib_kurtosis": kurtosis,
        "vib_skewness": skewness,
    }


def extract_features(
    vibration: np.ndarray,
    current_rms: float,
    temperature_c: float,
    cfg: AssetClassConfig,
) -> dict[str, float]:
    """Ubah satu blok getaran mentah jadi vektor ciri siap kirim.

    vibration adalah blok 10 detik pada laju cuplik kelas alat, dalam g.
    """
    vibration = np.asarray(vibration, dtype=np.float64)
    freqs, amp = averaged_amplitude_spectrum(vibration, cfg)
    nyquist = cfg.nyquist_hz
    corr = _energy_correction(cfg.window_size)

    out: dict[str, float] = {}
    out.update(_time_features(vibration))

    shaft = cfg.shaft_hz
    for order in (1, 2, 3):
        out["ord_%dx" % order] = _peak_near(
            freqs, amp, shaft * order, cfg.order_tolerance_hz
        )

    for label, target in cfg.defect_frequencies().items():
        out["%s_energy" % label] = _defect_energy(
            freqs,
            amp,
            target,
            cfg.defect_tolerance_hz,
            cfg.defect_harmonics,
            nyquist,
            corr,
        )

    for i in range(len(BAND_EDGES_HZ) - 1):
        lo, hi = BAND_EDGES_HZ[i], BAND_EDGES_HZ[i + 1]
        out["band_%d_%d" % (lo, hi)] = _band_rms(freqs, amp, lo, hi, corr)

    power = amp**2
    total_power = float(power.sum())
    if total_power > 0.0:
        out["spec_centroid"] = float(np.sum(freqs * power) / total_power)
        out["hf_ratio"] = float(power[freqs >= 800.0].sum() / total_power)
    else:
        out["spec_centroid"] = 0.0
        out["hf_ratio"] = 0.0

    out["current_rms"] = float(current_rms)
    out["temperature_c"] = float(temperature_c)

    missing = set(FEATURE_NAMES) - set(out)
    if missing:
        raise AssertionError("ciri hilang dari vektor: %s" % sorted(missing))
    return {name: out[name] for name in FEATURE_NAMES}


def to_vector(features: dict[str, float]) -> np.ndarray:
    """Susun dict ciri jadi array berurutan sesuai skema."""
    return np.array([features[name] for name in FEATURE_NAMES], dtype=np.float64)
