from datetime import datetime, timedelta, timezone

import numpy as np

from siaga_ai.projection import project

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def series(values, step_minutes=10):
    return [T0 + timedelta(minutes=step_minutes * i) for i in range(len(values))], np.array(values, dtype=float)


def test_flat_trend_gives_no_projection():
    ts, h = series([90, 91, 89, 90, 90, 91, 90, 89])
    assert project(ts, h, 40) is None


def test_rising_trend_gives_no_projection():
    ts, h = series(np.linspace(50, 90, 12))
    assert project(ts, h, 40) is None


def test_linear_decline_hits_threshold_at_expected_time():
    # turun 10 poin per jam dari 90: ambang 40 dicapai 5 jam setelah titik pertama.
    ts, h = series([90 - 10 * (i / 6) for i in range(13)])  # 2 jam data, tiap 10 menit
    p = project(ts, h, 40)
    assert p is not None
    # sisa dari titik terakhir (jam ke-2) ke jam ke-5 = 3 jam = 0.125 hari
    assert abs(p.days - 0.125) < 0.01
    assert p.low <= p.days <= (p.high if p.high is not None else float("inf"))


def test_already_below_threshold_gives_zero():
    ts, h = series(np.linspace(60, 20, 12))
    p = project(ts, h, 40)
    assert p is not None and p.days == 0.0


def test_nan_points_are_ignored():
    ts, h = series([90, np.nan, 85, 80, np.nan, 70, 65, np.nan, 55])
    p = project(ts, h, 40)
    assert p is not None and p.points == 6


def test_too_few_points():
    ts, h = series([90, 80, 70])
    assert project(ts, h, 40) is None
