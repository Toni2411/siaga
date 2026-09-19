"""Pemilihan jendela baseline yang tidak melintasi shutdown.

Setelah alat berhenti lama lalu dinyalakan lagi, "normal"-nya berubah: suhu,
dudukan, pelumasan, beban. Pada dataset IMS set 1, rig berhenti enam hari di
awal rekaman dan setelah itu seluruh pita energi bergeser lima sampai sepuluh
MAD secara permanen; model yang baseline-nya diambil sebelum jeda itu menilai
alat sehat sebagai rusak selama sebulan. Dengan baseline yang dimulai setelah
restart, model yang sama bertahan empat minggu dan sembilan restart berikutnya.

Aturannya: jendela baseline dimulai setelah jeda data terakhir yang lebih
panjang dari max_gap_h di dalam kandidat jendela. Jeda diukur pada cuplikan
yang berjalan; cuplikan saat alat mati tidak dihitung sebagai data.

Ambangnya sengaja dua hari, bukan beberapa jam. Pada set 1 rig berhenti tiap
satu dua hari (akhir pekan, malam) dan model yang dilatih melintasi jeda
20 jam sampai 4 hari tetap benar selama sebulan; hanya jeda enam hari di
awal, sesudah masa run-in bearing baru, yang mengubah normal. Ambang yang
terlalu pendek menggeser baseline dari jeda ke jeda sampai jatuh di masa
degradasi, dan model belajar "rusak" sebagai normal.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

DEFAULT_MAX_GAP_H = 48.0


def baseline_start(ts, running, started: datetime, days: float,
                   max_gap_h: float = DEFAULT_MAX_GAP_H) -> datetime:
    """Waktu mulai baseline efektif: `started`, atau setelah jeda panjang terakhir.

    Hanya jeda di dalam [started, started + days] yang dipertimbangkan; jeda
    setelah jendela penuh tidak menggeser apa pun, karena model yang sudah
    dilatih memang dibiarkan hidup melewati restart berikutnya.
    """
    run_ts = [t for t, r in zip(ts, running) if r and t >= started]
    if len(run_ts) < 2:
        return started
    window_end = started + timedelta(days=days)
    gap = timedelta(hours=max_gap_h)
    effective = started
    for a, b in zip(run_ts, run_ts[1:]):
        if a > window_end:
            break  # pasangan sepenuhnya di luar jendela
        if b - a > gap:
            effective = b  # jeda bermula di dalam jendela: mulai ulang setelahnya
            window_end = effective + timedelta(days=days)
    return effective


def baseline_mask(ts, running, started: datetime, days: float,
                  max_gap_h: float = DEFAULT_MAX_GAP_H):
    """Mask cuplikan baseline dan waktu mulai efektifnya."""
    start = baseline_start(ts, running, started, days, max_gap_h)
    end = start + timedelta(days=days)
    mask = np.array([(start <= t <= end) for t in ts]) & np.asarray(running, dtype=bool)
    return mask, start, end
