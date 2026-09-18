"""Pemutar ulang dataset bearing IMS sebagai aliran waktu nyata.

Dataset IMS berisi cuplikan satu detik tiap sepuluh menit, empat bearing pada
satu poros, direkam sampai salah satunya rusak. Di sini tiap kanal diperlakukan
sebagai satu alat terpisah, dan cap waktu dataset (2004) digeser ke jendela
waktu virtual supaya terlihat sebagai riwayat yang baru saja terjadi.

Gelombang dibaca dari cache .npz yang dibuat scripts/prepare_dataset.py, sudah
diturunkan ke laju cuplik edge. Kalau cache belum ada, jalankan skrip itu dulu.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import numpy as np

from . import Block

DEFAULT_SOURCE_IDS = ("PUMP-01", "PUMP-02", "PUMP-03", "PUMP-04")


class IMSReplay:
    """Iterator Block dari cache IMS, dipacu oleh faktor kecepatan.

    speed=1 memutar pada kecepatan asli (satu cuplikan tiap sepuluh menit).
    speed=600 memutar satu cuplikan tiap detik. speed=0 tanpa jeda sama sekali,
    berguna untuk mengisi riwayat atau untuk pengujian.
    """

    def __init__(
        self,
        cache_path: str | Path,
        source_ids: tuple[str, ...] = DEFAULT_SOURCE_IDS,
        speed: float = 600.0,
        start: datetime | None = None,
        first: int = 0,
        limit: int | None = None,
        max_sleep_s: float = 60.0,
    ):
        cache_path = Path(cache_path)
        if not cache_path.exists():
            raise FileNotFoundError(
                "cache dataset tidak ada: %s. Jalankan scripts/prepare_dataset.py dulu." % cache_path
            )
        data = np.load(cache_path)
        self.waves = data["waves"]  # (n_snapshot, n_channel, n_samples) float32
        self.files = [str(f) for f in data["files"]]
        self.dataset_ts = [datetime.fromisoformat(str(t)) for t in data["ts"]]
        self.sample_rate_hz = int(data["sample_rate_hz"]) if "sample_rate_hz" in data else 3200
        self.dataset_name = str(data["dataset"]) if "dataset" in data else "IMS"

        n_channels = self.waves.shape[1]
        if len(source_ids) < n_channels:
            raise ValueError(
                "cache punya %d kanal tapi hanya %d source_id diberikan" % (n_channels, len(source_ids))
            )
        self.source_ids = tuple(source_ids[:n_channels])
        self.speed = float(speed)
        self.max_sleep_s = max_sleep_s

        self.first = max(0, first)
        self.last = len(self.files) if limit is None else min(len(self.files), self.first + limit)

        # Geser cap waktu: default jendela berakhir sekarang, sehingga grafik
        # membaca sebagai riwayat beberapa hari terakhir.
        span = self.dataset_ts[self.last - 1] - self.dataset_ts[self.first]
        if start is None:
            start = datetime.now(timezone.utc) - span
        if start.tzinfo is None:
            raise ValueError("start harus timezone-aware")
        self.start = start
        self._offset = start - self.dataset_ts[self.first].replace(tzinfo=timezone.utc)

    @property
    def snapshots(self) -> int:
        return self.last - self.first

    def virtual_ts(self, index: int) -> datetime:
        return self.dataset_ts[index].replace(tzinfo=timezone.utc) + self._offset

    def __iter__(self) -> Iterator[Block]:
        clock = time.monotonic()
        for i in range(self.first, self.last):
            ts = self.virtual_ts(i)
            for ch, source_id in enumerate(self.source_ids):
                yield Block(
                    source_id=source_id,
                    ts=ts,
                    wave=self.waves[i, ch].astype(np.float64),
                    sample_rate_hz=self.sample_rate_hz,
                    origin={
                        "dataset": self.dataset_name,
                        "file": self.files[i],
                        "channel": ch,
                        "index": i,
                    },
                )
            if self.speed > 0 and i + 1 < self.last:
                real_gap = (self.dataset_ts[i + 1] - self.dataset_ts[i]).total_seconds()
                clock += min(real_gap / self.speed, self.max_sleep_s)
                delay = clock - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    clock = time.monotonic()  # tertinggal, jangan menumpuk hutang


def describe(cache_path: str | Path) -> dict:
    """Ringkasan cache tanpa memuat gelombang ke memori."""
    data = np.load(Path(cache_path))
    ts = [datetime.fromisoformat(str(t)) for t in data["ts"]]
    return {
        "snapshots": int(data["waves"].shape[0]),
        "channels": int(data["waves"].shape[1]),
        "samples": int(data["waves"].shape[2]),
        "first": ts[0].isoformat(),
        "last": ts[-1].isoformat(),
        "span": str(ts[-1] - ts[0]),
    }
