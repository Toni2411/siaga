from datetime import datetime, timedelta, timezone

import numpy as np

from siaga_ai.config import MODEL_FEATURES
from siaga_ai.evaluate import evaluate_channel


def synthetic(n_healthy=300, n_bad=40, seed=0):
    """Tiga hari sehat tiap sepuluh menit, lalu BPFO naik bertahap sampai 6x."""
    rng = np.random.default_rng(seed)
    n = n_healthy + n_bad
    X = np.abs(rng.normal(1.0, 0.1, (n, len(MODEL_FEATURES))))
    i = MODEL_FEATURES.index("bpfo_energy")
    X[n_healthy:, i] *= np.linspace(1.5, 6.0, n_bad)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = [t0 + timedelta(minutes=10 * k) for k in range(n)]
    running = np.ones(n, dtype=bool)
    return ts, X, running


def test_degradation_is_detected_with_lead_and_symptom():
    ts, X, running = synthetic()
    row = evaluate_channel(ts, X, running, baseline_days=1.0, trigger=40, recover=55,
                           cycles=3, healthy_margin_h=8.0, label="bpfo")
    assert row["baseline_n"] == 145  # 24 jam inklusif: 0..1440 menit tiap 10 menit
    assert row["false_alarms"] == 0
    assert row["trigger_at"] is not None
    assert 0 < row["lead_h"] < 8
    assert row["symptom"] == "bpfo"


def test_healthy_unit_never_triggers():
    ts, X, running = synthetic(n_bad=0, n_healthy=400)
    row = evaluate_channel(ts, X, running, 1.0, 40, 55, 3, 8.0, label=None)
    assert row["trigger_at"] is None
    assert row["false_alarms"] == 0
    assert row["healthy_median"] > 75
