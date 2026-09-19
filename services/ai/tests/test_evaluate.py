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


def test_baseline_starts_after_long_gap():
    from siaga_ai.baseline import baseline_start
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 6 jam data, berhenti 3 hari, lalu lanjut
    ts = [t0 + timedelta(minutes=10 * k) for k in range(36)]
    ts += [t0 + timedelta(days=3, minutes=10 * k) for k in range(300)]
    running = np.ones(len(ts), dtype=bool)
    assert baseline_start(ts, running, t0, days=1.0) == t0 + timedelta(days=3)


def test_routine_stop_does_not_move_baseline():
    from siaga_ai.baseline import baseline_start
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 6 jam data, berhenti semalam (12 jam), lanjut: masih baseline yang sama
    ts = [t0 + timedelta(minutes=10 * k) for k in range(36)]
    ts += [t0 + timedelta(hours=18, minutes=10 * k) for k in range(300)]
    running = np.ones(len(ts), dtype=bool)
    assert baseline_start(ts, running, t0, days=1.0) == t0


def test_baseline_ignores_gap_after_window():
    from siaga_ai.baseline import baseline_start
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = [t0 + timedelta(minutes=10 * k) for k in range(200)]          # 33 jam penuh
    ts += [t0 + timedelta(days=5, minutes=10 * k) for k in range(50)]  # jeda jauh setelah jendela
    running = np.ones(len(ts), dtype=bool)
    assert baseline_start(ts, running, t0, days=1.0) == t0
