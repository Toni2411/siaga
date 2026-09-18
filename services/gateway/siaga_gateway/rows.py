"""Ubah satu pesan jadi baris tabel. Murni, tanpa I/O, supaya mudah diuji."""

from __future__ import annotations

from datetime import datetime

from siaga_edge.message import parse_ts, validate


def reading_rows(msg: dict) -> list[tuple[datetime, str, str, float, int]]:
    """Baris untuk sensor_reading: (ts, source_id, feature, value, schema_version)."""
    validate(msg)
    ts = parse_ts(msg["ts"])
    source = msg["source_id"]
    version = int(msg["schema_version"])
    return [(ts, source, name, float(value), version) for name, value in msg["features"].items()]


def state_row(msg: dict) -> tuple[datetime, str, str]:
    """Baris untuk operating_state: (ts, source_id, state)."""
    return (parse_ts(msg["ts"]), msg["source_id"], msg["operating_state"])
