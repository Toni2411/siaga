"""Penulis ke TimescaleDB."""

from __future__ import annotations

import logging

import psycopg

from .rows import reading_rows, state_row

log = logging.getLogger("siaga.gateway.store")

INSERT_READINGS = """
INSERT INTO sensor_reading (ts, source_id, feature, value, schema_version)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (source_id, feature, ts) DO NOTHING
"""

INSERT_STATE = """
INSERT INTO operating_state (ts, source_id, state)
VALUES (%s, %s, %s)
ON CONFLICT (source_id, ts) DO NOTHING
"""


class TimescaleStore:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn: psycopg.Connection | None = None
        self.messages = 0
        self.rows = 0

    def connect(self) -> None:
        self.conn = psycopg.connect(self.dsn, autocommit=False)
        log.info("terhubung ke %s", _redact(self.dsn))

    def write(self, msg: dict) -> int:
        """Simpan satu pesan. Mengembalikan jumlah baris ciri yang ditulis."""
        return self.write_many([msg])

    def write_many(self, msgs: list[dict]) -> int:
        """Simpan sekumpulan pesan dalam satu transaksi.

        Satu transaksi per pesan terlalu lambat, sekitar sepuluh pesan per
        detik karena tiap commit bolak balik ke database. Dengan batch, ribuan
        pesan per detik masuk tanpa mengubah apa pun di tabel.
        """
        assert self.conn is not None, "connect() dulu"
        if not msgs:
            return 0
        readings = []
        states = []
        for msg in msgs:
            readings.extend(reading_rows(msg))
            states.append(state_row(msg))
        try:
            with self.conn.cursor() as cur:
                cur.executemany(INSERT_READINGS, readings)
                cur.executemany(INSERT_STATE, states)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        self.messages += len(msgs)
        self.rows += len(readings)
        return len(readings)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None


def _redact(dsn: str) -> str:
    # jangan bocorkan password ke log
    if "@" in dsn and "://" in dsn:
        head, tail = dsn.split("://", 1)
        creds, host = tail.split("@", 1)
        user = creds.split(":", 1)[0]
        return "%s://%s:***@%s" % (head, user, host)
    return dsn
