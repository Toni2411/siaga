"""Baca vektor ciri dari TimescaleDB dalam bentuk lebar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import psycopg

from .config import MODEL_FEATURES


@dataclass
class FeatureFrame:
    ts: list[datetime]          # timezone-aware, urut naik
    X: np.ndarray               # (n, len(features))
    state: list[str]            # kondisi operasi per baris
    features: tuple[str, ...]

    def __len__(self):
        return len(self.ts)

    @property
    def running(self) -> np.ndarray:
        return np.array([s == "stabil" for s in self.state], dtype=bool)


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn)


def load_features(conn, source_id: str, since: datetime | None = None,
                  features: tuple[str, ...] = MODEL_FEATURES) -> FeatureFrame:
    """Semua cuplikan satu sumber setelah `since` (eksklusif), dipivot ke matriks.

    Baris tanpa status operasi dibuang: gateway selalu menulis keduanya dalam
    satu transaksi, jadi ketiadaannya berarti data rusak.
    """
    sql = """
        select r.ts, r.feature, r.value, s.state
        from sensor_reading r
        join operating_state s on s.source_id = r.source_id and s.ts = r.ts
        where r.source_id = %s and r.feature = any(%s)
    """
    params: list = [source_id, list(features)]
    if since is not None:
        sql += " and r.ts > %s"
        params.append(since)
    sql += " order by r.ts"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    ts = sorted({r[0] for r in rows})
    index = {t: i for i, t in enumerate(ts)}
    col = {f: i for i, f in enumerate(features)}
    X = np.full((len(ts), len(features)), np.nan)
    state = [""] * len(ts)
    for t, f, v, s in rows:
        X[index[t], col[f]] = v
        state[index[t]] = s

    # buang baris yang tidak lengkap
    complete = ~np.isnan(X).any(axis=1)
    return FeatureFrame(
        ts=[t for t, ok in zip(ts, complete) if ok],
        X=X[complete],
        state=[s for s, ok in zip(state, complete) if ok],
        features=features,
    )


def latest_ts(conn, source_id: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("select max(ts) from sensor_reading where source_id = %s", (source_id,))
        row = cur.fetchone()
    return row[0] if row else None
