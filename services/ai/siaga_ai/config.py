"""Pengaturan dari environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from siaga_edge.schema import FEATURE_NAMES

# Arus dan suhu disintesis di v1 (dataset tidak memuatnya) dan sengaja tidak
# diberi informasi degradasi. Model tidak boleh melihatnya, supaya tidak ada
# kesan model belajar dari sesuatu yang tidak pernah diukur.
EXCLUDED_FEATURES = ("current_rms", "temperature_c")
MODEL_FEATURES = tuple(f for f in FEATURE_NAMES if f not in EXCLUDED_FEATURES)


@dataclass
class Settings:
    timescale_dsn: str = field(default_factory=lambda: os.environ.get(
        "SIAGA_TIMESCALE_DSN", "postgresql://siaga:siaga@localhost:5432/siaga_ts"))
    erpnext_url: str = field(default_factory=lambda: os.environ.get("SIAGA_ERPNEXT_URL", "http://localhost:8080"))
    erpnext_api_key: str = field(default_factory=lambda: os.environ.get("ERPNEXT_API_KEY", ""))
    erpnext_api_secret: str = field(default_factory=lambda: os.environ.get("ERPNEXT_API_SECRET", ""))
    model_dir: str = field(default_factory=lambda: os.environ.get("SIAGA_MODEL_DIR", "data/models"))
    interval_s: float = field(default_factory=lambda: float(os.environ.get("SIAGA_AI_INTERVAL", "30")))

    # Minimal cuplikan sehat sebelum model per unit boleh dilatih.
    min_baseline_rows: int = 50
    # Jendela riwayat untuk proyeksi tren, dalam jam waktu data.
    projection_window_h: float = 24.0
    # Batch penulisan Health Score ke ERPNext.
    insert_batch: int = 200
