"""Proyeksi waktu menuju ambang dari tren skor kesehatan.

Ini sengaja bukan model regresi sisa umur. Regresi sisa umur menuntut data run
to failure yang banyak, dan proyek ini tidak memilikinya. Yang dilakukan hanya
ekstrapolasi linear tren skor terakhir ke ambang pemicu, dengan interval dari
ketidakpastian kemiringan. Disebut apa adanya: proyeksi tren.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

SECONDS_PER_DAY = 86400.0
MAX_DAYS = 365.0


@dataclass
class Projection:
    days: float          # perkiraan hari sampai skor menyentuh ambang
    low: float           # batas bawah (kemiringan lebih curam)
    high: float | None   # batas atas; None kalau kemiringan bisa jadi datar
    slope_per_day: float
    points: int


def project(ts: list[datetime], health: np.ndarray, threshold: float,
            min_points: int = 6, min_decline_per_day: float = 0.5) -> Projection | None:
    """Ekstrapolasi tren linear ke ambang. None kalau tidak ada tren turun yang berarti."""
    health = np.asarray(health, dtype=float)
    ok = np.isfinite(health)
    if ok.sum() < min_points:
        return None
    t = np.array([(x - ts[0]).total_seconds() for x in ts])[ok] / SECONDS_PER_DAY
    h = health[ok]
    if np.ptp(t) <= 0:
        return None

    A = np.vstack([t, np.ones_like(t)]).T
    coef, residuals, _, _ = np.linalg.lstsq(A, h, rcond=None)
    slope, intercept = coef
    n = len(t)

    # galat baku kemiringan
    if n > 2:
        resid = h - (slope * t + intercept)
        se = np.sqrt(np.sum(resid ** 2) / (n - 2) / np.sum((t - t.mean()) ** 2))
    else:
        se = 0.0
    steep = slope - 1.96 * se
    shallow = slope + 1.96 * se

    # Tren harus turun secara berarti dan signifikan. Derau kecil di jendela
    # pendek menghasilkan kemiringan besar per hari, tapi galat bakunya juga
    # besar; syarat shallow < 0 menyingkirkan itu.
    if slope > -min_decline_per_day or shallow >= 0:
        return None

    fitted_last = slope * t[-1] + intercept
    if fitted_last <= threshold:
        return Projection(0.0, 0.0, 0.0, float(slope), n)

    def days_for(s):
        if s >= 0:
            return None
        return float(min(MAX_DAYS, (fitted_last - threshold) / (-s)))

    return Projection(
        days=days_for(slope),
        low=days_for(steep) if days_for(steep) is not None else 0.0,
        high=days_for(shallow),
        slope_per_day=float(slope),
        points=n,
    )
