import numpy as np
import pytest

from siaga_ai.config import MODEL_FEATURES
from siaga_ai.model import UnitModel


def baseline(n=200, seed=0):
    rng = np.random.default_rng(seed)
    X = np.abs(rng.normal(1.0, 0.1, (n, len(MODEL_FEATURES))))
    return X


@pytest.fixture
def model():
    return UnitModel.fit(baseline(), MODEL_FEATURES)


def test_synthetic_scalars_are_excluded():
    assert "current_rms" not in MODEL_FEATURES
    assert "temperature_c" not in MODEL_FEATURES


def test_healthy_data_scores_high(model):
    h, _ = model.health(baseline(seed=1))
    assert np.median(h) > 75
    assert np.percentile(h, 5) > 55  # di atas ambang pulih, histeresis tidak terganggu
    assert (h < 40).mean() < 0.01


def test_bpfo_spike_scores_low_and_is_explained(model):
    x = np.ones(len(MODEL_FEATURES))
    i = MODEL_FEATURES.index("bpfo_energy")
    x[i] = 6.0  # enam kali baseline
    h, _ = model.health(x)
    assert h[0] < 40
    devs = model.explain(x)
    assert devs[0].feature == "bpfo_energy"
    assert devs[0].ratio == pytest.approx(6.0, rel=0.2)
    assert model.symptom(x)[0] == "bpfo"
    assert "cacat outer race" in model.summary(x, devs)


def test_broadband_rise_is_labelled_broadband(model):
    # pita dan RMS naik bersama, ciri bearing dan orde poros tetap: jangan menuduh bearing
    x = np.ones(len(MODEL_FEATURES))
    for i, f in enumerate(MODEL_FEATURES):
        if f.startswith("band_") or f in ("vib_rms", "vib_peak", "vib_p2p", "hf_ratio"):
            x[i] = 3.0
    assert model.symptom(x)[0] == "broadband"
    assert "getaran lebar" in model.summary(x)


def test_small_bpfo_rise_below_edge_is_not_a_bearing_symptom(model):
    x = np.ones(len(MODEL_FEATURES))
    x[MODEL_FEATURES.index("bpfo_energy")] = 1.15  # sedikit di atas baseline
    assert model.symptom(x)[0] == "broadband"


def test_health_is_monotone_in_deviation(model):
    xs = []
    for k in (1.0, 1.5, 2.5, 4.0, 8.0):
        x = np.ones(len(MODEL_FEATURES))
        x[MODEL_FEATURES.index("vib_rms")] = k
        xs.append(x)
    h, _ = model.health(np.array(xs))
    assert all(h[i] >= h[i + 1] - 1e-9 for i in range(len(h) - 1))


def test_confidence_from_baseline_size():
    small = UnitModel.fit(baseline(n=36), MODEL_FEATURES)
    assert small.confidence() == pytest.approx(25.0)
    assert UnitModel.fit(baseline(n=300), MODEL_FEATURES).confidence() == 100.0


def test_too_small_baseline_rejected():
    with pytest.raises(ValueError):
        UnitModel.fit(baseline(n=5), MODEL_FEATURES)


def test_save_and_load_roundtrip(model, tmp_path):
    p = model.save(tmp_path / "unit.joblib")
    again = UnitModel.load(p)
    x = baseline(n=3, seed=2)
    assert np.allclose(again.health(x)[0], model.health(x)[0])
    assert again.version == model.version
