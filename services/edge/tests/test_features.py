"""Uji ekstraksi ciri.

Berkas ini juga jadi spesifikasi kebenaran saat DSP diporting ke ESP-DSP di
v1.5. Firmware dianggap lulus kalau menghasilkan angka yang sama untuk
gelombang uji yang sama, dalam toleransi yang sama.
"""

import math

import numpy as np
import pytest

from siaga_edge import FEATURE_COUNT, FEATURE_NAMES, IMS_PUMP_CLASS, extract_features
from siaga_edge.config import AssetClassConfig

# Kelas uji dengan poros 50 Hz, kelipatan tepat dari lebar bin 3.125 Hz,
# supaya uji akurasi amplitudo tidak terganggu scalloping loss.
BIN_ALIGNED = AssetClassConfig(
    name="uji bin aligned",
    rpm=3000.0,
    rolling_elements=16,
    ball_diameter_mm=8.4074,
    pitch_diameter_mm=71.501,
    contact_angle_deg=15.17,
)


def signal(cfg, seconds=2.0, tones=(), noise=0.0, seed=1):
    n = int(seconds * cfg.sample_rate_hz)
    t = np.arange(n) / cfg.sample_rate_hz
    x = np.zeros(n)
    for freq, amp in tones:
        x += amp * np.sin(2.0 * np.pi * freq * t)
    if noise > 0.0:
        x += np.random.default_rng(seed).normal(0.0, noise, n)
    return x


def features(cfg, **kw):
    return extract_features(signal(cfg, **kw), current_rms=12.0, temperature_c=55.0, cfg=cfg)


class TestSchema:
    def test_vector_has_25_features(self):
        assert FEATURE_COUNT == 25

    def test_names_are_unique(self):
        assert len(set(FEATURE_NAMES)) == FEATURE_COUNT

    def test_extract_returns_full_vector_in_schema_order(self):
        out = features(BIN_ALIGNED, tones=[(50.0, 1.0)])
        assert list(out) == list(FEATURE_NAMES)

    def test_scalar_channels_pass_through(self):
        out = features(BIN_ALIGNED, tones=[(50.0, 1.0)])
        assert out["current_rms"] == pytest.approx(12.0)
        assert out["temperature_c"] == pytest.approx(55.0)


class TestDefectFrequencies:
    """Frekuensi cacat bearing Rexnord ZA-2115 pada rig IMS, poros 2000 RPM.

    Angka rujukannya 236.4 Hz dan 296.9 Hz, nilai yang lazim dikutip untuk
    dataset ini. Ini menguji rumus geometri, bukan DSP.
    """

    def test_bpfo(self):
        assert IMS_PUMP_CLASS.bpfo_hz == pytest.approx(236.4, abs=0.5)

    def test_bpfi(self):
        assert IMS_PUMP_CLASS.bpfi_hz == pytest.approx(296.9, abs=0.5)

    def test_all_defect_frequencies_below_nyquist(self):
        # Pembenaran pilihan 3.2 kHz: seluruh pita cacat masih terbaca.
        for name, freq in IMS_PUMP_CLASS.defect_frequencies().items():
            assert 0 < freq < IMS_PUMP_CLASS.nyquist_hz, name

    def test_second_harmonics_also_below_nyquist(self):
        for name, freq in IMS_PUMP_CLASS.defect_frequencies().items():
            assert freq * 2 < IMS_PUMP_CLASS.nyquist_hz, name


class TestTimeDomain:
    def test_rms_of_sine(self):
        out = features(BIN_ALIGNED, tones=[(100.0, 2.0)])
        assert out["vib_rms"] == pytest.approx(2.0 / math.sqrt(2), rel=0.01)

    def test_crest_factor_of_sine(self):
        out = features(BIN_ALIGNED, tones=[(100.0, 2.0)])
        assert out["vib_crest"] == pytest.approx(math.sqrt(2), rel=0.01)

    def test_kurtosis_of_gaussian_noise_is_three(self):
        out = features(BIN_ALIGNED, seconds=10.0, noise=1.0)
        assert out["vib_kurtosis"] == pytest.approx(3.0, abs=0.2)

    def test_kurtosis_rises_with_impulses(self):
        cfg = BIN_ALIGNED
        base = signal(cfg, seconds=10.0, noise=1.0)
        spiky = base.copy()
        spiky[:: cfg.sample_rate_hz // 8] += 12.0  # ketukan periodik ala cacat
        healthy = extract_features(base, 12.0, 55.0, cfg)
        faulty = extract_features(spiky, 12.0, 55.0, cfg)
        assert faulty["vib_kurtosis"] > 2 * healthy["vib_kurtosis"]
        assert faulty["vib_crest"] > healthy["vib_crest"]


class TestSpectrum:
    def test_order_amplitude_is_recovered(self):
        out = features(BIN_ALIGNED, tones=[(50.0, 2.0), (100.0, 1.0), (150.0, 0.5)])
        assert out["ord_1x"] == pytest.approx(2.0, rel=0.02)
        assert out["ord_2x"] == pytest.approx(1.0, rel=0.02)
        assert out["ord_3x"] == pytest.approx(0.5, rel=0.02)

    def test_band_rms_matches_time_domain_rms_for_single_tone(self):
        # Satu tone di 500 Hz: RMS pita yang memuatnya harus sama dengan RMS
        # keseluruhan. Ini yang membuktikan koreksi energi jendela benar.
        out = features(BIN_ALIGNED, tones=[(500.0, 2.0)])
        assert out["band_400_600"] == pytest.approx(2.0 / math.sqrt(2), rel=0.02)
        assert out["band_400_600"] == pytest.approx(out["vib_rms"], rel=0.02)

    def test_band_energy_stays_in_its_own_band(self):
        out = features(BIN_ALIGNED, tones=[(500.0, 2.0)])
        assert out["band_400_600"] > 10 * out["band_1000_1200"]
        assert out["band_400_600"] > 10 * out["band_0_200"]

    def test_high_frequency_ratio_follows_content(self):
        low = features(BIN_ALIGNED, tones=[(300.0, 1.0)])
        high = features(BIN_ALIGNED, tones=[(1200.0, 1.0)])
        assert low["hf_ratio"] < 0.05
        assert high["hf_ratio"] > 0.95
        assert high["spec_centroid"] > low["spec_centroid"]


class TestBearingFaultDiscrimination:
    """Inti nilai sistem: membedakan cacat outer race dari inner race."""

    def _healthy(self, cfg):
        return signal(cfg, seconds=10.0, tones=[(cfg.shaft_hz, 0.5)], noise=0.3)

    def _with_outer_race_defect(self, cfg):
        x = self._healthy(cfg)
        t = np.arange(x.size) / cfg.sample_rate_hz
        for h, amp in ((1, 1.2), (2, 0.6)):
            x = x + amp * np.sin(2.0 * np.pi * cfg.bpfo_hz * h * t)
        return x

    def test_outer_race_defect_raises_bpfo_energy(self):
        cfg = BIN_ALIGNED
        healthy = extract_features(self._healthy(cfg), 12.0, 55.0, cfg)
        faulty = extract_features(self._with_outer_race_defect(cfg), 12.0, 55.0, cfg)
        assert faulty["bpfo_energy"] > 5 * healthy["bpfo_energy"]

    def test_outer_race_defect_leaves_bpfi_alone(self):
        # Kalau ini gagal, sistem tidak bisa menyebut komponen mana yang rusak,
        # dan penjelasan pemicu di work order jadi tidak berarti.
        cfg = BIN_ALIGNED
        healthy = extract_features(self._healthy(cfg), 12.0, 55.0, cfg)
        faulty = extract_features(self._with_outer_race_defect(cfg), 12.0, 55.0, cfg)
        assert faulty["bpfi_energy"] < 2 * healthy["bpfi_energy"]

    def test_shaft_order_untouched_by_bearing_defect(self):
        cfg = BIN_ALIGNED
        healthy = extract_features(self._healthy(cfg), 12.0, 55.0, cfg)
        faulty = extract_features(self._with_outer_race_defect(cfg), 12.0, 55.0, cfg)
        assert faulty["ord_1x"] == pytest.approx(healthy["ord_1x"], rel=0.1)


class TestContract:
    def test_deterministic(self):
        x = signal(BIN_ALIGNED, tones=[(50.0, 1.0)], noise=0.2)
        first = extract_features(x, 12.0, 55.0, BIN_ALIGNED)
        second = extract_features(x, 12.0, 55.0, BIN_ALIGNED)
        assert first == second

    def test_block_shorter_than_window_is_rejected(self):
        with pytest.raises(ValueError):
            extract_features(np.zeros(512), 12.0, 55.0, BIN_ALIGNED)

    def test_silent_input_does_not_divide_by_zero(self):
        out = extract_features(np.zeros(3200), 0.0, 25.0, BIN_ALIGNED)
        assert out["vib_crest"] == 0.0
        assert out["vib_kurtosis"] == 0.0
        assert all(math.isfinite(v) for v in out.values())
