"""Kontrak pesan vektor ciri di MQTT.

Ini batas antara edge dan sisa sistem. Virtual edge hari ini dan firmware ESP32
di v1.5 harus menghasilkan pesan yang lolos validate() di sini, dan gateway
menolak apa pun yang tidak lolos.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from .schema import FEATURE_NAMES, SCHEMA_VERSION

TOPIC_PREFIX = "siaga/edge"
OPERATING_STATES = ("mati", "start", "stabil", "berbeban")


def topic_for(source_id: str) -> str:
    return "%s/%s/features" % (TOPIC_PREFIX, source_id)


def build(
    source_id: str,
    ts: datetime,
    features: dict[str, float],
    operating_state: str,
    sample_rate_hz: int,
    samples: int,
    origin: dict | None = None,
    synthetic: tuple[str, ...] = (),
) -> dict:
    """Susun satu pesan. ts harus timezone-aware, disimpan sebagai UTC."""
    if ts.tzinfo is None:
        raise ValueError("ts harus timezone-aware")
    if operating_state not in OPERATING_STATES:
        raise ValueError("operating_state tidak dikenal: %r" % operating_state)

    msg = {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id,
        "ts": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "operating_state": operating_state,
        "features": {name: float(features[name]) for name in FEATURE_NAMES},
        "block": {"sample_rate_hz": int(sample_rate_hz), "samples": int(samples)},
    }
    if origin:
        msg["origin"] = origin
    if synthetic:
        # Ciri yang tidak berasal dari pengukuran. Disebut terang terangan
        # supaya tidak ada yang mengira dataset memuatnya.
        msg["synthetic"] = list(synthetic)
    return msg


def validate(msg: dict) -> None:
    """Lempar ValueError kalau pesan tidak memenuhi kontrak."""
    if not isinstance(msg, dict):
        raise ValueError("pesan bukan objek")
    if msg.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            "schema_version %r, gateway ini hanya menerima %d"
            % (msg.get("schema_version"), SCHEMA_VERSION)
        )
    if not msg.get("source_id"):
        raise ValueError("source_id kosong")
    if msg.get("operating_state") not in OPERATING_STATES:
        raise ValueError("operating_state tidak dikenal: %r" % msg.get("operating_state"))

    try:
        parse_ts(msg["ts"])
    except (KeyError, ValueError) as e:
        raise ValueError("ts tidak valid: %s" % e)

    features = msg.get("features")
    if not isinstance(features, dict):
        raise ValueError("features bukan objek")
    missing = [n for n in FEATURE_NAMES if n not in features]
    if missing:
        raise ValueError("ciri hilang: %s" % missing)
    extra = [n for n in features if n not in FEATURE_NAMES]
    if extra:
        raise ValueError("ciri tidak dikenal: %s" % extra)
    for name, value in features.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("ciri %s bukan angka: %r" % (name, value))
        if not math.isfinite(value):
            raise ValueError("ciri %s tidak finite: %r" % (name, value))


def parse_ts(value: str) -> datetime:
    """Terima ISO 8601 dengan Z atau offset; hasil selalu timezone-aware."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError("timestamp tanpa zona waktu")
    return ts


def dumps(msg: dict) -> bytes:
    return json.dumps(msg, separators=(",", ":")).encode()


def loads(payload: bytes) -> dict:
    msg = json.loads(payload)
    validate(msg)
    return msg
